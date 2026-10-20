#!/usr/bin/env python3
"""Generate all app icon assets for iOS and Android from the master artwork."""
import json
import os
from PIL import Image

BASE = os.path.expanduser("~/workspace/chess-mobile")
MASTER = os.path.join(
    BASE,
    "assets/media-generation-app-icon-fullbleed-0-ddf5f4d8-910f-4394-8c30-16574dd24973.webp",
)
IOS_ICONSET = os.path.join(BASE, "ios/App/App/Assets.xcassets/AppIcon.appiconset")
AND_RES = os.path.join(BASE, "android/app/src/main/res")

master = Image.open(MASTER).convert("RGB")
print("master:", master.size)

# Sample gradient colors from the artwork for the Android adaptive background
w, h = master.size
top = master.getpixel((int(w * 0.08), int(h * 0.06)))
bottom = master.getpixel((int(w * 0.92), int(h * 0.94)))
mid = master.getpixel((int(w * 0.5), int(h * 0.5)))
def hx(c):
    return "#%02x%02x%02x" % c
print("top:", hx(top), "mid:", hx(mid), "bottom:", hx(bottom))

# ---------------- iOS ----------------
os.makedirs(IOS_ICONSET, exist_ok=True)
ios_specs = [
    ("AppIcon-1024.png", 1024, "ios-marketing", "1x", "1024x1024"),
    ("AppIcon-180.png", 180, "iphone", "3x", "60x60"),
    ("AppIcon-120.png", 120, "iphone", "2x", "60x60"),
    ("AppIcon-120.png", 120, "iphone", "3x", "40x40"),
    ("AppIcon-87.png", 87, "iphone", "3x", "29x29"),
    ("AppIcon-80.png", 80, "iphone", "2x", "40x40"),
    ("AppIcon-58.png", 58, "iphone", "2x", "29x29"),
    ("AppIcon-167.png", 167, "ipad", "2x", "83.5x83.5"),
    ("AppIcon-152.png", 152, "ipad", "2x", "76x76"),
    ("AppIcon-80.png", 80, "ipad", "2x", "40x40"),
    ("AppIcon-58.png", 58, "ipad", "2x", "29x29"),
    ("AppIcon-40.png", 40, "ipad", "1x", "40x40"),
    ("AppIcon-29.png", 29, "ipad", "1x", "29x29"),
]
made = set()
images = []
for fname, px, idiom, scale, size in ios_specs:
    if fname not in made:
        master.resize((px, px), Image.LANCZOS).save(
            os.path.join(IOS_ICONSET, fname), "PNG"
        )
        made.add(fname)
    images.append(
        {"filename": fname, "idiom": idiom, "scale": scale, "size": size}
    )
with open(os.path.join(IOS_ICONSET, "Contents.json"), "w") as f:
    json.dump(
        {"images": images, "info": {"author": "xcode", "version": 1}}, f, indent=2
    )
print("iOS icons:", len(made))

# ---------------- Android ----------------
# Legacy launcher icons (full artwork)
densities = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
for d, px in densities.items():
    ddir = os.path.join(AND_RES, f"mipmap-{d}")
    os.makedirs(ddir, exist_ok=True)
    master.resize((px, px), Image.LANCZOS).save(
        os.path.join(ddir, "ic_launcher.png"), "PNG"
    )

# Adaptive foreground: artwork scaled to 68% centered on transparency
fg_dens = {"mdpi": 108, "hdpi": 162, "xhdpi": 216, "xxhdpi": 324, "xxxhdpi": 432}
for d, px in fg_dens.items():
    ddir = os.path.join(AND_RES, f"mipmap-{d}")
    fg = Image.new("RGBA", (px, px), (0, 0, 0, 0))
    inner = int(px * 0.68)
    art = master.resize((inner, inner), Image.LANCZOS).convert("RGBA")
    fg.paste(art, ((px - inner) // 2, (px - inner) // 2), art)
    fg.save(os.path.join(ddir, "ic_launcher_foreground.png"), "PNG")

# Splash logo (512px)
draw = os.path.join(AND_RES, "drawable")
os.makedirs(draw, exist_ok=True)
master.resize((512, 512), Image.LANCZOS).save(
    os.path.join(draw, "splash_logo.png"), "PNG"
)

# Adaptive icon XMLs
anydpi = os.path.join(AND_RES, "mipmap-anydpi-v26")
os.makedirs(anydpi, exist_ok=True)
adaptive = """<?xml version="1.0" encoding="utf-8"?>
<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">
    <background android:drawable="@drawable/ic_launcher_background"/>
    <foreground android:drawable="@mipmap/ic_launcher_foreground"/>
</adaptive-icon>
"""
for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
    with open(os.path.join(anydpi, name), "w") as f:
        f.write(adaptive)

# Background gradient drawable (sampled from artwork)
with open(os.path.join(draw, "ic_launcher_background.xml"), "w") as f:
    f.write(
        f"""<?xml version="1.0" encoding="utf-8"?>
<shape xmlns:android="http://schemas.android.com/apk/res/android" android:shape="rectangle">
    <gradient android:angle="135" android:startColor="{hx(top)}" android:endColor="{hx(bottom)}" android:type="linear"/>
</shape>
"""
    )

# Splash drawable
with open(os.path.join(draw, "splash.xml"), "w") as f:
    f.write(
        """<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:drawable="@color/splash_background"/>
    <item>
        <bitmap android:gravity="center" android:src="@drawable/splash_logo"/>
    </item>
</layer-list>
"""
    )

# Colors: create values/colors.xml with our splash color (the Capacitor
# library AAR already provides colorPrimary/colorPrimaryDark/colorAccent,
# so the app only needs to define its own additions).
colors_path = os.path.join(AND_RES, "values/colors.xml")
with open(colors_path, "w") as f:
    f.write(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<resources>\n"
        '    <color name="splash_background">#1a1a2e</color>\n'
        "</resources>\n"
    )

print("Android icons + splash done")
print("bg gradient:", hx(top), "->", hx(bottom))
