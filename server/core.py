"""Listeners, sessions, the packet capture log and the local account store."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import secrets
import ssl
import threading
from pathlib import Path

from . import components, tdf
from .frame import FRAMINGS, MSG_TYPE_NAMES, PING, PING_REPLY, Packet

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: Path) -> dict:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    for key in ("data_dir", "log_dir", "tls_cert", "tls_key"):
        if cfg.get(key):
            cfg[key] = str((ROOT / cfg[key]).resolve())
    return cfg


class Accounts:
    """Tiny JSON-file account store. Good enough until we need a real DB."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.data = {"next_id": 1000000001, "by_token": {}}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def get_or_create(self, token: str) -> dict:
        with self.lock:
            key = token or "anonymous"
            user = self.data["by_token"].get(key)
            if user is None:
                uid = self.data["next_id"]
                self.data["next_id"] += 1
                user = {"id": uid, "name": f"Player{uid % 10000:04d}",
                        "created": dt.datetime.now().isoformat(timespec="seconds")}
                self.data["by_token"][key] = user
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            return user


class CaptureLog:
    """Writes every packet (both directions) as one JSON line. This is the main
    research tool once a real game client connects."""

    def __init__(self, log_dir: Path, enabled: bool) -> None:
        self.enabled = enabled
        self.lock = threading.Lock()
        if enabled:
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            self.path = log_dir / f"capture-{stamp}.jsonl"

    def write(self, listener: str, peer: str, direction: str, p: Packet) -> None:
        if not self.enabled:
            return
        fields, err = tdf.decode_safe(p.body)
        rec = {
            "t": dt.datetime.now().isoformat(timespec="milliseconds"),
            "listener": listener, "peer": peer, "dir": direction,
            "component": p.component, "component_name": components.component_name(p.component),
            "command": p.command, "command_name": components.command_name(p.component, p.command),
            "type": MSG_TYPE_NAMES.get(p.msg_type, p.msg_type), "msg_num": p.msg_num,
            "error": p.error, "body_hex": p.body.hex(), "metadata_hex": p.metadata.hex(),
            "decoded": [f.to_json() for f in fields], "decode_error": err,
        }
        self._append(rec)

    def write_raw(self, listener: str, peer: str, kind: str, data: bytes) -> None:
        if self.enabled:
            self._append({"t": dt.datetime.now().isoformat(timespec="milliseconds"),
                          "listener": listener, "peer": peer, "dir": kind, "raw_hex": data.hex()})

    def _append(self, rec: dict) -> None:
        with self.lock, self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")


HANDSHAKE_TYPES = {0: "HelloRequest", 1: "ClientHello", 2: "ServerHello", 4: "NewSessionTicket",
                   11: "Certificate", 12: "ServerKeyExchange", 13: "CertificateRequest",
                   14: "ServerHelloDone", 15: "CertificateVerify", 16: "ClientKeyExchange",
                   20: "Finished"}
ALERTS = {0: "close_notify", 10: "unexpected_message", 20: "bad_record_mac", 40: "handshake_failure",
          42: "bad_certificate", 43: "unsupported_certificate", 44: "certificate_revoked",
          45: "certificate_expired", 46: "certificate_unknown", 47: "illegal_parameter",
          48: "unknown_ca", 50: "decode_error", 51: "decrypt_error", 70: "protocol_version",
          71: "insufficient_security", 80: "internal_error", 112: "unrecognized_name"}


def describe_tls_records(data: bytes) -> list[str]:
    """Name each TLS record in a chunk (plaintext part of the handshake only)."""
    out, p, encrypted = [], 0, False
    while p + 5 <= len(data):
        ctype, length = data[p], int.from_bytes(data[p + 3:p + 5], "big")
        body = data[p + 5:p + 5 + length]
        if ctype == 22 and not encrypted:
            q, names = 0, []
            while q + 4 <= len(body):
                names.append(HANDSHAKE_TYPES.get(body[q], f"hs{body[q]}"))
                q += 4 + int.from_bytes(body[q + 1:q + 4], "big")
            out.append("+".join(names) or "handshake")
        elif ctype == 22:
            out.append("encrypted handshake (Finished)")
        elif ctype == 20:
            out.append("ChangeCipherSpec")
            encrypted = True
        elif ctype == 21:
            if len(body) == 2 and not encrypted:
                out.append(f"ALERT {'fatal' if body[0] == 2 else 'warning'} "
                           f"{ALERTS.get(body[1], body[1])}")
            else:
                out.append("ALERT (encrypted)")
        elif ctype == 23:
            out.append("application data")
        else:
            out.append(f"record type {ctype}")
        p += 5 + length
    if p < len(data):
        out.append(f"{len(data) - p} trailing bytes")
    return out


def tls_verdict(trail: list[str], err: Exception) -> str:
    """Plain-language guess at why the handshake failed."""
    text = " ".join(trail)
    if "ALERT" in text:
        return "client sent a TLS alert (see above) - that names the reason"
    if "ClientKeyExchange" in text:
        return "client got past our certificate (sent ClientKeyExchange) - cert was ACCEPTED, failure is later"
    if trail and all("ClientHello" in t for t in trail):
        return ("client hung up right after receiving our certificate, without an alert - "
                "most likely it REJECTED the certificate")
    return "unclear - see client records"


class Session:
    def __init__(self, server: "Server", listener: str, reader, writer,
                 tls_ctx: ssl.SSLContext | None = None) -> None:
        self.server = server
        self.listener = listener
        self.reader = reader
        self.writer = writer
        peer = writer.get_extra_info("peername")
        self.peer = f"{peer[0]}:{peer[1]}" if peer else "?"
        self.framing = FRAMINGS[server.cfg.get("framing", "fire2")]
        self.session_key = secrets.token_hex(16)
        self.user: dict | None = None
        self.tls_ctx = tls_ctx

    def log(self, msg: str) -> None:
        self.server.log(f"[{self.listener} {self.peer}] {msg}")

    # --- transport: plain TCP, or TLS through memory BIOs ------------------
    # TLS is driven by hand (ssl.MemoryBIO) instead of asyncio's start_tls so we
    # can log every TLS record the client sends. That tells us exactly where in
    # the handshake a client gives up (e.g. right after seeing our certificate).

    async def _write_raw(self, data: bytes) -> None:
        self.writer.write(data)
        await self.writer.drain()

    async def _flush_tls(self, note: str | None = None) -> None:
        data = self.tls_out.read()
        if data:
            if note:
                self.log(f"TLS -> sent {note}: {', '.join(describe_tls_records(data))}")
            await self._write_raw(data)

    async def _handshake(self) -> bool:
        self.tls_in, self.tls_out = ssl.MemoryBIO(), ssl.MemoryBIO()
        self.tls = self.tls_ctx.wrap_bio(self.tls_in, self.tls_out, server_side=True)
        trail: list[str] = []
        try:
            while True:
                try:
                    self.tls.do_handshake()
                    break
                except ssl.SSLWantReadError:
                    await self._flush_tls("our flight")
                    chunk = await asyncio.wait_for(self.reader.read(65536), timeout=30)
                    if not chunk:
                        raise ConnectionResetError("client closed the connection")
                    recs = describe_tls_records(chunk)
                    trail += recs
                    self.log(f"TLS <- client sent: {', '.join(recs)}")
                    if chunk[0] == 0x16 and len(chunk) > 5 and chunk[5] == 1:
                        self.server.capture.write_raw(self.listener, self.peer, "tls_hello", chunk)
                    self.tls_in.write(chunk)
            await self._flush_tls("handshake finish")
        except (ssl.SSLError, ConnectionError, asyncio.TimeoutError, OSError) as e:
            reason = getattr(e, "reason", None) or type(e).__name__
            if not trail and isinstance(e, ConnectionError):
                self.log("closed before sending a TLS hello (probably start.bat's port check)")
                return False
            try:
                await self._flush_tls("alert")
            except OSError:
                pass
            verdict = tls_verdict(trail, e)
            self.log(f"TLS handshake FAILED: {reason} ({e}). Client records: "
                     f"{' | '.join(trail) or 'none'}. => {verdict}")
            self.server.capture.write_raw(self.listener, self.peer, "tls_fail",
                                          json.dumps({"reason": str(reason), "error": str(e),
                                                      "client_records": trail,
                                                      "verdict": verdict}).encode())
            return False
        self.log(f"TLS handshake OK: {self.tls.version()} {self.tls.cipher()[0]} "
                 f"sni={self.server.last_sni}")
        return True

    async def _recv(self) -> bytes:
        if self.tls is None:
            return await self.reader.read(65536)
        while True:
            try:
                return self.tls.read(65536)
            except ssl.SSLWantReadError:
                chunk = await self.reader.read(65536)
                if not chunk:
                    return b""
                self.tls_in.write(chunk)
            except ssl.SSLZeroReturnError:
                return b""

    async def send(self, p: Packet) -> None:
        self.server.capture.write(self.listener, self.peer, "out", p)
        data = self.framing.write(p)
        if self.tls is None:
            await self._write_raw(data)
        else:
            self.tls.write(data)
            await self._flush_tls()

    async def run(self) -> None:
        self.log("connected")
        self.tls = None
        if self.tls_ctx is not None and not await self._handshake():
            self.writer.close()
            return
        buf = bytearray()
        first = True
        try:
            while True:
                chunk = await self._recv()
                if not chunk:
                    break
                if first and chunk[0] == 0x16 and self.tls is None:
                    # 0x16 = TLS handshake record. Key Phase 1 signal: this port needs TLS.
                    self.log(f"client is speaking TLS on a plain listener! hello={chunk[:64].hex()}")
                    self.server.capture.write_raw(self.listener, self.peer, "tls_hello", chunk)
                first = False
                buf += chunk
                while (p := self.framing.try_read(buf)) is not None:
                    await self.dispatch(p)
        except (ConnectionError, ssl.SSLError) as e:
            self.log(f"connection error: {e}")
        finally:
            self.log("disconnected")
            self.writer.close()

    async def dispatch(self, p: Packet) -> None:
        self.server.capture.write(self.listener, self.peer, "in", p)
        name = f"{components.component_name(p.component)}.{components.command_name(p.component, p.command)}"
        if p.msg_type == PING:
            await self.send(Packet(p.component, p.command, PING_REPLY, p.msg_num))
            return
        fields, err = tdf.decode_safe(p.body)
        handler = components.HANDLERS.get((p.component, p.command))
        if handler is None:
            policy = self.server.cfg.get("unknown_commands", "empty_reply")
            self.log(f"UNHANDLED {name} ({p.component}/{p.command}) - policy {policy}")
            if policy == "empty_reply":
                await self.send(p.reply(b""))
            elif policy == "error":
                await self.send(p.error_reply(0x4000))  # placeholder error code
            return
        self.log(f"-> {name}" + (f" (decode problem: {err})" if err else ""))
        result = handler(self, p, fields)
        for out in (result if isinstance(result, list) else [result] if result else []):
            await self.send(out)


class Server:
    def __init__(self, cfg: dict) -> None:
        self.cfg = cfg
        data_dir = Path(cfg.get("data_dir", ROOT / "data"))
        log_dir = Path(cfg.get("log_dir", ROOT / "logs"))
        self.accounts = Accounts(data_dir / "accounts.json")
        self.capture = CaptureLog(log_dir, cfg.get("capture", True))

    def log(self, msg: str) -> None:
        print(f"{dt.datetime.now():%H:%M:%S} {msg}", flush=True)

    def _ssl(self, section: dict) -> ssl.SSLContext | None:
        if not section.get("tls"):
            return None
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        # EA's ProtoSSL client is old; allow legacy protocol versions/ciphers.
        ctx.minimum_version = ssl.TLSVersion.TLSv1
        ctx.set_ciphers("ALL:@SECLEVEL=0")
        ctx.load_cert_chain(self.cfg["tls_cert"], self.cfg["tls_key"])

        def on_sni(sslobj, name, _ctx):
            self.last_sni = name

        ctx.sni_callback = on_sni
        return ctx

    async def serve(self) -> None:
        servers = []
        self.last_sni = None
        for name in ("redirector", "blaze"):
            section = self.cfg[name]
            ctx = self._ssl(section)

            async def on_conn(r, w, _name=name, _ctx=ctx):
                await Session(self, _name, r, w, _ctx).run()

            srv = await asyncio.start_server(on_conn, self.cfg["bind"], section["port"])
            tls = "TLS" if section.get("tls") else "plain TCP"
            self.log(f"{name} listening on {self.cfg['bind']}:{section['port']} ({tls})")
            servers.append(srv)
        if self.capture.enabled:
            self.log(f"capturing packets to {self.capture.path}")
        self.log(f"framing={self.cfg.get('framing', 'fire2')} service={self.cfg['service_name']}")
        await asyncio.gather(*(s.serve_forever() for s in servers))
