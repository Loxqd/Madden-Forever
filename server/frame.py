"""Blaze packet framing.

Two header layouts are publicly documented:

* "fire2" - 16-byte header used by Frostbite-era Blaze (seen in the Mirror's
  Edge Catalyst emulator grid-leak/blaze, 2016). Madden NFL 20 is a 2019
  Frostbite title, so this is our best guess and the default.
* "fire"  - 12-byte header (+2 for jumbo packets) used by older Blaze 3 games
  (Mass Effect 3, Battlefield 3). Kept as a fallback.

Which one Madden 20 actually uses is UNVERIFIED until we capture real traffic.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

# Message types (fire2 stores these in the top 3 bits of byte 12)
MESSAGE = 0
REPLY = 1
NOTIFICATION = 2
ERROR_REPLY = 3
PING = 4
PING_REPLY = 5

MSG_TYPE_NAMES = {MESSAGE: "request", REPLY: "reply", NOTIFICATION: "notify",
                  ERROR_REPLY: "error", PING: "ping", PING_REPLY: "pong"}


@dataclass
class Packet:
    component: int
    command: int
    msg_type: int = MESSAGE
    msg_num: int = 0
    error: int = 0
    body: bytes = b""
    metadata: bytes = b""

    def reply(self, body: bytes = b"") -> "Packet":
        return Packet(self.component, self.command, REPLY, self.msg_num, 0, body)

    def error_reply(self, code: int, body: bytes = b"") -> "Packet":
        return Packet(self.component, self.command, ERROR_REPLY, self.msg_num, code, body)


class Fire2:
    """u32 payload | u16 meta | u16 comp | u16 cmd | u24 msgnum | u8 type<<5 | u8 opts | u8 rsvd"""

    name = "fire2"
    HEADER = 16

    @staticmethod
    def try_read(buf: bytearray) -> Packet | None:
        if len(buf) < Fire2.HEADER:
            return None
        payload, meta = struct.unpack_from(">IH", buf, 0)
        total = Fire2.HEADER + meta + payload
        if len(buf) < total:
            return None
        comp, cmd = struct.unpack_from(">HH", buf, 6)
        msg_num = (buf[10] << 16) | (buf[11] << 8) | buf[12]
        msg_type = buf[13] >> 5
        metadata = bytes(buf[16:16 + meta])
        body = bytes(buf[16 + meta:total])
        del buf[:total]
        return Packet(comp, cmd, msg_type, msg_num, 0, body, metadata)

    @staticmethod
    def write(p: Packet) -> bytes:
        n = p.msg_num & 0xFFFFFF
        head = struct.pack(">IHHH", len(p.body), len(p.metadata), p.component, p.command)
        head += bytes([(n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF, (p.msg_type & 7) << 5, 0, 0])
        return head + p.metadata + p.body


class Fire:
    """u16 len | u16 comp | u16 cmd | u16 error | u16 qtype | u16 id [| u16 extlen]"""

    name = "fire"
    HEADER = 12

    @staticmethod
    def try_read(buf: bytearray) -> Packet | None:
        if len(buf) < Fire.HEADER:
            return None
        length, comp, cmd, err, qtype, pid = struct.unpack_from(">HHHHHH", buf, 0)
        head = Fire.HEADER
        if qtype & 0x0010:
            if len(buf) < 14:
                return None
            length |= struct.unpack_from(">H", buf, 12)[0] << 16
            head = 14
        if len(buf) < head + length:
            return None
        body = bytes(buf[head:head + length])
        del buf[:head + length]
        return Packet(comp, cmd, (qtype >> 12) & 0xF, pid, err, body)

    @staticmethod
    def write(p: Packet) -> bytes:
        n = len(p.body)
        qtype = (p.msg_type & 0xF) << 12
        if n > 0xFFFF:
            qtype |= 0x0010
            head = struct.pack(">HHHHHHH", n & 0xFFFF, p.component, p.command, p.error,
                               qtype, p.msg_num & 0xFFFF, n >> 16)
        else:
            head = struct.pack(">HHHHHH", n, p.component, p.command, p.error, qtype,
                               p.msg_num & 0xFFFF)
        return head + p.body


FRAMINGS = {"fire2": Fire2, "fire": Fire}
