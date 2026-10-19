"""Pretend to be the game: redirector -> Blaze -> preAuth/login/ping.

Proves the skeleton answers end to end without a game install.
Usage:  python tools/fake_client.py [--host 127.0.0.1] [--port 42230]
Exit code 0 = every step got a reply.
"""

from __future__ import annotations

import argparse
import json
import socket
import ssl
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import tdf  # noqa: E402
from server.frame import FRAMINGS, MESSAGE, PING, Packet  # noqa: E402
from server.tdf import Writer  # noqa: E402


class Conn:
    def __init__(self, host: str, port: int, framing, tls: bool = False) -> None:
        self.sock = socket.create_connection((host, port), timeout=5)
        if tls:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE  # test client only: accept our self-signed cert
            self.sock = ctx.wrap_socket(self.sock, server_hostname="spring18.gosredirector.ea.com")
        self.framing = framing
        self.buf = bytearray()
        self.num = 0

    def call(self, comp: int, cmd: int, body: bytes = b"", msg_type: int = MESSAGE) -> Packet:
        self.num += 1
        self.sock.sendall(self.framing.write(Packet(comp, cmd, msg_type, self.num, 0, body)))
        while (p := self.framing.try_read(self.buf)) is None:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("server closed the connection")
            self.buf += chunk
        if p.msg_num != self.num:
            raise RuntimeError(f"reply msg_num {p.msg_num} != request {self.num}")
        return p


def show(label: str, p: Packet) -> list:
    fields = tdf.decode(p.body)
    print(f"  {label}: type={p.msg_type} {json.dumps([f.to_json() for f in fields])[:300]}")
    return fields


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=42230)
    ap.add_argument("--framing", default="fire2", choices=sorted(FRAMINGS))
    ap.add_argument("--tls", action="store_true", help="redirector uses TLS")
    a = ap.parse_args()
    framing = FRAMINGS[a.framing]

    print(f"1. redirector {a.host}:{a.port}" + (" (TLS)" if a.tls else ""))
    r = Conn(a.host, a.port, framing, a.tls)
    req = Writer().str("NAME", "madden-2020-pc").str("PLAT", "pc").str("CLNT", "fake_client")
    addr = show("getServerInstance", r.call(5, 1, req.bytes()))
    valu = tdf.find(addr, "ADDR").field.value
    host, port = tdf.find(valu, "HOST"), tdf.find(valu, "PORT")

    print(f"2. blaze {host}:{port}")
    b = Conn(host, port, framing)
    show("preAuth", b.call(9, 7))
    login = show("login", b.call(1, 10, Writer().str("AUTH", "fake-token-123").bytes()))
    name = tdf.find(tdf.find(tdf.find(login, "SESS"), "PDTL"), "DSNM")
    print(f"     -> logged in as {name}")
    show("ping", b.call(9, 2))
    show("unknown custom 2060/801 (empty reply expected)", b.call(2060, 801))
    print(f"  fire ping -> type={b.call(0, 0, msg_type=PING).msg_type} (5 = pong)")
    print("OK - all steps answered")
    return 0


if __name__ == "__main__":
    sys.exit(main())
