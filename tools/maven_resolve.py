#!/usr/bin/env python3
"""Recursively resolve Maven POMs and download artifacts into a local repo.

Uses curl (which works through this environment's proxy) to fetch from
Google Maven and Maven Central, then lays out a file:// Maven repository
that Gradle can use with --offline.
"""
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

REPOS = [
    "https://dl.google.com/dl/android/maven2",
    "https://repo.maven.apache.org/maven2",
]
DEST = "/home/hatch/m2repo"
NS = {"m": "http://maven.apache.org/POM/4.0.0"}

stats = {"poms": 0, "artifacts": 0, "skipped": 0}
done = set()


def curl_dl(url, out):
    if os.path.exists(out) and os.path.getsize(out) > 0:
        return True
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = out + ".tmp"
    r = subprocess.run(
        ["curl", "-fSL", "--retry", "2", "--max-time", "90", "-o", tmp, url],
        capture_output=True,
    )
    if r.returncode == 0 and os.path.getsize(tmp) > 0:
        os.rename(tmp, out)
        return True
    if os.path.exists(tmp):
        os.remove(tmp)
    return False


def coord_path(group, artifact, version, ext):
    return os.path.join(
        DEST, group.replace(".", "/"), artifact, version,
        f"{artifact}-{version}.{ext}",
    )


def fetch(group, artifact, version, ext):
    dest = coord_path(group, artifact, version, ext)
    if os.path.exists(dest):
        return dest
    for repo in REPOS:
        url = f"{repo}/{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.{ext}"
        if curl_dl(url, dest):
            return dest
    return None


def txt(el, tag):
    c = el.find(f"m:{tag}", NS)
    return c.text.strip() if c is not None and c.text else ""


def subst(text, props):
    def rep(m):
        return props.get(m.group(1), m.group(0))
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r"\$\{([^}]+)\}", rep, text)
    return text


def parse_pom(path):
    tree = ET.parse(path)
    root = tree.getroot()
    return root


def collect(root, props):
    """Collect properties, depMgmt, dependencies, parent from a POM."""
    for p in root.findall("m:properties/m:*", NS):
        tag = p.tag.split("}", 1)[1]
        if p.text:
            props[tag] = p.text.strip()
    dep_mgmt = {}
    bom_imports = []
    for d in root.findall("m:dependencyManagement/m:dependencies/m:dependency", NS):
        g, a, v = txt(d, "groupId"), txt(d, "artifactId"), txt(d, "version")
        scope = txt(d, "scope")
        dtype = txt(d, "type")
        if scope == "import" and dtype == "pom" and g and a and v:
            bom_imports.append((g, a, subst(v, props)))
            continue
        if g and a and v:
            dep_mgmt[(g, a)] = v
    deps = []
    for d in root.findall("m:dependencies/m:dependency", NS):
        deps.append(d)
    parent = root.find("m:parent", NS)
    return dep_mgmt, deps, parent, bom_imports


def ver_key(v):
    """Sortable key for Maven versions."""
    parts = []
    for p in re.split(r"[.\-]", v):
        if p.isdigit():
            parts.append((0, int(p), ""))
        else:
            m = re.match(r"(\d+)(.*)", p)
            if m:
                parts.append((0, int(m.group(1)), m.group(2)))
            else:
                parts.append((1, 0, p))
    return parts


def resolve_range(group, artifact, range_spec):
    """Pick the highest available version satisfying a Maven range."""
    m = re.match(r"^([\[\(])([^,]*),?([^,\]]*)([\]\)])$", range_spec.strip())
    if not m:
        return None
    lo_inc, lo, hi, hi_inc = m.group(1) == "[", m.group(2), m.group(3), m.group(4) == "]"
    # metadata
    meta_path = f"{group.replace('.', '/')}/{artifact}/maven-metadata.xml"
    meta_dest = os.path.join(DEST, meta_path)
    versions = []
    for repo in REPOS:
        if curl_dl(f"{repo}/{meta_path}", meta_dest):
            try:
                root = ET.parse(meta_dest).getroot()
                # metadata has no namespace; try both
                vers = root.findall("versioning/versions/version")
                if not vers:
                    vers = root.findall("m:versioning/m:versions/m:version", NS)
                for v in vers:
                    versions.append(v.text.strip())
            except ET.ParseError:
                pass
            break
    cand = []
    for v in versions:
        k = ver_key(v)
        ok = True
        if lo:
            ok = ok and (k >= ver_key(lo) if lo_inc else k > ver_key(lo))
        if hi:
            ok = ok and (k <= ver_key(hi) if hi_inc else k < ver_key(hi))
        if ok:
            cand.append((k, v))
    if not cand:
        return None
    cand.sort()
    # prefer the highest stable version (no alpha/beta/rc); fall back to highest overall
    stable = [(k, v) for k, v in cand
              if not re.search(r"alpha|beta|rc|m[0-9]|preview", v, re.I)]
    return (stable or cand)[-1][1]


def bom_dep_mgmt(group, artifact, version, props, depth=0):
    """Fetch a BOM POM and return its dependencyManagement map."""
    if depth > 4:
        return {}
    version = subst(version, props)
    pom = fetch(group, artifact, version, "pom")
    if not pom:
        return {}
    stats["poms"] += 1
    root = parse_pom(pom)
    bprops = dict(props)
    # resolve parent chain for the BOM too
    chain = []
    p = root.find("m:parent", NS)
    while p is not None:
        pg, pa, pv = txt(p, "groupId"), txt(p, "artifactId"), txt(p, "version")
        if not (pg and pa and pv):
            break
        ppom = fetch(pg, pa, pv, "pom")
        if not ppom:
            break
        chain.append(parse_pom(ppom))
        p = chain[-1].find("m:parent", NS)
    for croot in reversed(chain):
        collect(croot, bprops)  # properties only; depMgmt from BOM parents is rare
    dm, _, _, boms = collect(root, bprops)
    out = {}
    for (g, a), v in dm.items():
        out[(subst(g, bprops), subst(a, bprops))] = subst(v, bprops)
    for bg, ba, bv in boms:
        out.update(bom_dep_mgmt(subst(bg, bprops), subst(ba, bprops),
                                subst(bv, bprops), bprops, depth + 1))
    return out


def resolve(group, artifact, version, stack=(), excluded=frozenset()):
    key = (group, artifact, version)
    if key in done or key in excluded:
        return
    if key in stack:
        return
    stack = stack + (key,)

    pom = fetch(group, artifact, version, "pom")
    if not pom:
        print(f"  WARN no pom for {group}:{artifact}:{version}", flush=True)
        return
    stats["poms"] += 1
    root = parse_pom(pom)

    # resolve parent chain for properties + depMgmt
    props = {}
    dep_mgmt = {}
    chain = []
    r, p = root, root.find("m:parent", NS)
    while p is not None:
        pg, pa, pv = txt(p, "groupId"), txt(p, "artifactId"), txt(p, "version")
        if not (pg and pa and pv):
            break
        ppom = fetch(pg, pa, pv, "pom")
        if not ppom:
            break
        chain.append(parse_pom(ppom))
        p = chain[-1].find("m:parent", NS)
    # implicit Maven project properties (inherit from DIRECT parent if missing)
    # MUST be set before collect() so BOM versions like ${project.version} resolve
    _pg = txt(root, "groupId")
    _pv = txt(root, "version")
    if chain:
        if not _pg:
            _pg = txt(chain[0], "groupId")
        if not _pv:
            _pv = txt(chain[0], "version")
    props.setdefault("project.groupId", _pg)
    props.setdefault("project.artifactId", txt(root, "artifactId"))
    props.setdefault("project.version", _pv)
    props.setdefault("project.group", _pg)

    for croot in reversed(chain):
        c_dm, _, _, c_boms = collect(croot, props)
        dep_mgmt.update({k: v for k, v in c_dm.items()})
        for bg, ba, bv in c_boms:
            dep_mgmt.update(bom_dep_mgmt(bg, ba, bv, props))
    c_dm, deps, _, boms = collect(root, props)
    dep_mgmt.update(c_dm)
    for bg, ba, bv in boms:
        dep_mgmt.update(bom_dep_mgmt(bg, ba, bv, props))

    packaging = txt(root, "packaging") or "jar"
    # download the artifact itself (unless pom packaging)
    if packaging in ("jar", "aar", "bundle"):
        ext = "aar" if packaging == "aar" else "jar"
        # check <type> override? packaging is enough
        if fetch(group, artifact, version, ext):
            stats["artifacts"] += 1
        else:
            print(f"  WARN no {ext} for {group}:{artifact}:{version}", flush=True)

    for d in deps:
        scope = txt(d, "scope") or "compile"
        if scope not in ("compile", "runtime"):
            continue
        if txt(d, "optional") == "true":
            continue
        dg = subst(txt(d, "groupId"), props)
        da = subst(txt(d, "artifactId"), props)
        dv = subst(txt(d, "version"), props)
        if not dv:
            dv = dep_mgmt.get((dg, da), "")
            dv = subst(dv, props)
        if not (dg and da and dv):
            continue
        if dv.startswith("[") or dv.startswith("("):
            rv = resolve_range(dg, da, dv)
            if rv:
                print(f"  range {dv} -> {rv} for {dg}:{da}", flush=True)
                dv = rv
            else:
                print(f"  WARN range {dv} for {dg}:{da}, skipping", flush=True)
                continue
        # exclusions declared by this dependency apply to its transitive tree
        excl = set(excluded)
        for e in d.findall("m:exclusions/m:exclusion", NS):
            excl.add((txt(e, "groupId"), txt(e, "artifactId")))
        resolve(dg, da, dv, stack, frozenset(excl))

    done.add(key)


ROOTS = [
    ("com.android.tools.build", "gradle", "8.13.0"),
    ("org.bouncycastle", "bcutil-jdk18on", "1.79"),
    ("org.glassfish.jaxb", "txw2", "2.3.2"),
    ("androidx.appcompat", "appcompat-resources", "1.7.1"),
    ("com.android.tools.build", "aapt2", "8.13.0-13719691"),
    ("com.android.tools.lint", "lint-gradle", "31.13.0"),
    ("com.google.gms", "google-services", "4.4.4"),
    ("androidx.appcompat", "appcompat", "1.7.1"),
    ("androidx.coordinatorlayout", "coordinatorlayout", "1.3.0"),
    ("androidx.core", "core-splashscreen", "1.2.0"),
    ("androidx.core", "core", "1.17.0"),
    ("androidx.activity", "activity", "1.11.0"),
    ("androidx.fragment", "fragment", "1.8.9"),
    ("androidx.webkit", "webkit", "1.14.0"),
    ("org.apache.cordova", "framework", "14.0.1"),
    ("junit", "junit", "4.13.2"),
    ("androidx.test.ext", "junit", "1.3.0"),
    ("androidx.test.espresso", "espresso-core", "3.7.0"),
]

if __name__ == "__main__":
    for g, a, v in ROOTS:
        print(f"resolving {g}:{a}:{v}", flush=True)
        resolve(g, a, v)
    print(f"DONE poms={stats['poms']} artifacts={stats['artifacts']}", flush=True)
