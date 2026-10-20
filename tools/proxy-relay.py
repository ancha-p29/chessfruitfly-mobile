#!/usr/bin/env python3
"""Local CONNECT relay: adds upstream proxy auth so Java/Gradle works.

Listens on 127.0.0.1:8888 without auth, forwards CONNECT requests to the
environment's egress proxy with the proper Proxy-Authorization header.
"""
import base64
import os
import socket
import threading
from urllib.parse import urlparse

_up = urlparse(os.environ["https_proxy"])
UPSTREAM = (_up.hostname, _up.port or 3128)
AUTH = base64.b64encode(f"{_up.username}:{_up.password}".encode()).decode()
LISTEN = ("127.0.0.1", 8888)


def pipe(a, b):
    try:
        while True:
            d = a.recv(65536)
            if not d:
                break
            b.sendall(d)
    except OSError:
        pass


def handle(client):
    up = None
    try:
        req = b""
        while b"\r\n\r\n" not in req:
            chunk = client.recv(4096)
            if not chunk:
                return
            req += chunk
            if len(req) > 65536:
                return
        line = req.split(b"\r\n")[0].decode("latin1")
        parts = line.split()
        if len(parts) < 2 or parts[0] != "CONNECT":
            client.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        target = parts[1]
        print(f"CONNECT {target}", flush=True)
        up = socket.create_connection(UPSTREAM, timeout=20)
        up.sendall(
            f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n"
            f"Proxy-Authorization: Basic {AUTH}\r\n\r\n".encode()
        )
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = up.recv(4096)
            if not chunk:
                break
            resp += chunk
        status = resp.split(b"\r\n")[0] if resp else b""
        if b" 200 " not in status:
            print(f"UPSTREAM FAIL {target}: {status[:60]!r}", flush=True)
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return
        client.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        t = threading.Thread(target=pipe, args=(up, client), daemon=True)
        t.start()
        pipe(client, up)
        t.join(timeout=1)
    except OSError:
        pass
    finally:
        for s in (client, up):
            try:
                if s:
                    s.close()
            except OSError:
                pass


def main():
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(LISTEN)
    srv.listen(100)
    print(f"relay listening on {LISTEN[0]}:{LISTEN[1]}", flush=True)
    while True:
        c, _ = srv.accept()
        threading.Thread(target=handle, args=(c,), daemon=True).start()


if __name__ == "__main__":
    main()
