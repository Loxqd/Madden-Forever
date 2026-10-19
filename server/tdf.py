"""TDF ("Tag Data Format") encoder/decoder for EA Blaze packet bodies.

The wire format is taken from public, permissively licensed work (the MIT
`tdf` Rust crate by jacobtread, used by Pocket Relay for Mass Effect 3).
Nothing here is verified against Madden NFL 20 yet - see docs/protocol-notes.md.

Every value in a body is `tag (3 bytes) + type (1 byte) + payload`. A tag is
up to four characters (A-Z, 0-9) packed into 3 bytes.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

# Type ids (the 4th byte after a tag)
VARINT = 0x0
STRING = 0x1
BLOB = 0x2
GROUP = 0x3
LIST = 0x4
MAP = 0x5
UNION = 0x6
INTLIST = 0x7
OBJTYPE = 0x8
OBJID = 0x9
FLOAT = 0xA
GENERIC = 0xC

TYPE_NAMES = {
    VARINT: "int", STRING: "string", BLOB: "blob", GROUP: "group", LIST: "list",
    MAP: "map", UNION: "union", INTLIST: "intlist", OBJTYPE: "objtype",
    OBJID: "objid", FLOAT: "float", GENERIC: "generic",
}

UNION_UNSET = 0x7F


class TdfError(ValueError):
    pass


# --------------------------------------------------------------------------
# Tags

def encode_tag(tag: str) -> bytes:
    """Pack a tag of up to 4 chars into 3 bytes (same bit layout as the crate)."""
    t = tag.upper().encode("ascii")
    if not 1 <= len(t) <= 4:
        raise TdfError(f"bad tag {tag!r}")
    o = [0, 0, 0]
    if len(t) > 0:
        o[0] |= (t[0] & 0x40) << 1
        o[0] |= (t[0] & 0x10) << 2
        o[0] |= (t[0] & 0x0F) << 2
    if len(t) > 1:
        o[0] |= (t[1] & 0x40) >> 5
        o[0] |= (t[1] & 0x10) >> 4
        o[1] |= (t[1] & 0x0F) << 4
    if len(t) > 2:
        o[1] |= (t[2] & 0x40) >> 3
        o[1] |= (t[2] & 0x10) >> 2
        o[1] |= (t[2] & 0x0C) >> 2
        o[2] |= (t[2] & 0x03) << 6
    if len(t) > 3:
        o[2] |= (t[3] & 0x40) >> 1
        o[2] |= t[3] & 0x1F
    return bytes(b & 0xFF for b in o)


def decode_tag(b: bytes) -> str:
    def dec(m: int, c: int) -> int:
        if m | c == 0:
            return 0
        if m & 0x40 == 0:
            return 0x30 | c
        return m | c

    out = [
        dec((b[0] & 0x80) >> 1, (b[0] & 0x7C) >> 2),
        dec((b[0] & 2) << 5, ((b[0] & 1) << 4) | ((b[1] & 0xF0) >> 4)),
        dec((b[1] & 8) << 3, ((b[1] & 7) << 2) | ((b[2] & 0xC0) >> 6)),
        dec((b[2] & 0x20) << 1, b[2] & 0x1F),
    ]
    return "".join(chr(c) for c in out if c)


# --------------------------------------------------------------------------
# Writer

def encode_varint(value: int) -> bytes:
    """Blaze varint: first byte = continue(0x80) | sign(0x40) | 6 bits."""
    neg = value < 0
    v = -value if neg else value
    first = v & 0x3F
    if neg:
        first |= 0x40
    v >>= 6
    if v == 0:
        return bytes([first])
    out = bytearray([first | 0x80])
    while v >= 0x80:
        out.append((v & 0x7F) | 0x80)
        v >>= 7
    out.append(v)
    return bytes(out)


class Writer:
    """Builds a TDF body. Methods return self so calls can be chained."""

    def __init__(self) -> None:
        self.buf = bytearray()

    def bytes(self) -> bytes:
        return bytes(self.buf)

    # raw helpers -----------------------------------------------------
    def _tag(self, tag: str, ty: int) -> None:
        self.buf += encode_tag(tag) + bytes([ty])

    def _varint(self, v: int) -> None:
        self.buf += encode_varint(v)

    def _string(self, s: str) -> None:
        data = s.encode("utf-8") + b"\x00"
        self._varint(len(data))
        self.buf += data

    def _blob(self, b: bytes) -> None:
        self._varint(len(b))
        self.buf += b

    # tagged values ---------------------------------------------------
    def int(self, tag: str, v: int) -> "Writer":
        self._tag(tag, VARINT)
        self._varint(int(v))
        return self

    def str(self, tag: str, s: str) -> "Writer":
        self._tag(tag, STRING)
        self._string(s)
        return self

    def blob(self, tag: str, b: bytes) -> "Writer":
        self._tag(tag, BLOB)
        self._blob(b)
        return self

    def float(self, tag: str, f: float) -> "Writer":
        self._tag(tag, FLOAT)
        self.buf += struct.pack(">f", f)
        return self

    def group(self, tag: str, inner: "Writer") -> "Writer":
        self._tag(tag, GROUP)
        self.buf += inner.buf + b"\x00"
        return self

    def objtype(self, tag: str, component: int, type_: int) -> "Writer":
        self._tag(tag, OBJTYPE)
        self._varint(component)
        self._varint(type_)
        return self

    def objid(self, tag: str, component: int, type_: int, id_: int) -> "Writer":
        self._tag(tag, OBJID)
        self._varint(component)
        self._varint(type_)
        self._varint(id_)
        return self

    def intlist(self, tag: str, values: list[int]) -> "Writer":
        self._tag(tag, INTLIST)
        self._varint(len(values))
        for v in values:
            self._varint(v)
        return self

    def list_int(self, tag: str, values: list[int]) -> "Writer":
        self._tag(tag, LIST)
        self.buf.append(VARINT)
        self._varint(len(values))
        for v in values:
            self._varint(v)
        return self

    def list_str(self, tag: str, values: list[str]) -> "Writer":
        self._tag(tag, LIST)
        self.buf.append(STRING)
        self._varint(len(values))
        for v in values:
            self._string(v)
        return self

    def list_group(self, tag: str, groups: list["Writer"]) -> "Writer":
        self._tag(tag, LIST)
        self.buf.append(GROUP)
        self._varint(len(groups))
        for g in groups:
            self.buf += g.buf + b"\x00"
        return self

    def map_str_str(self, tag: str, m: dict[str, str]) -> "Writer":
        self._tag(tag, MAP)
        self.buf += bytes([STRING, STRING])
        self._varint(len(m))
        for k, v in m.items():
            self._string(k)
            self._string(v)
        return self

    def map_str_int(self, tag: str, m: dict[str, int]) -> "Writer":
        self._tag(tag, MAP)
        self.buf += bytes([STRING, VARINT])
        self._varint(len(m))
        for k, v in m.items():
            self._string(k)
            self._varint(v)
        return self

    def union_group(self, tag: str, key: int, inner_tag: str, inner: "Writer") -> "Writer":
        self._tag(tag, UNION)
        self.buf.append(key)
        self._tag(inner_tag, GROUP)
        self.buf += inner.buf + b"\x00"
        return self

    def union_unset(self, tag: str) -> "Writer":
        self._tag(tag, UNION)
        self.buf.append(UNION_UNSET)
        return self


# --------------------------------------------------------------------------
# Reader

@dataclass
class Field:
    tag: str
    type: int
    value: Any

    def to_json(self) -> Any:
        return {"tag": self.tag, "type": TYPE_NAMES.get(self.type, hex(self.type)),
                "value": _jsonable(self.value)}


@dataclass
class Union:
    key: int
    field: Field | None


@dataclass
class TList:
    elem_type: int
    items: list[Any] = field(default_factory=list)


@dataclass
class TMap:
    key_type: int
    value_type: int
    items: list[tuple[Any, Any]] = field(default_factory=list)


def _jsonable(v: Any) -> Any:
    if isinstance(v, Field):
        return v.to_json()
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    if isinstance(v, bytes):
        return {"hex": v.hex()}
    if isinstance(v, Union):
        return {"key": v.key, "field": _jsonable(v.field)}
    if isinstance(v, TList):
        return {"of": TYPE_NAMES.get(v.elem_type), "items": [_jsonable(x) for x in v.items]}
    if isinstance(v, TMap):
        return {"of": [TYPE_NAMES.get(v.key_type), TYPE_NAMES.get(v.value_type)],
                "items": [[_jsonable(k), _jsonable(x)] for k, x in v.items]}
    if isinstance(v, tuple):
        return list(v)
    return v


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0

    def _byte(self) -> int:
        if self.pos >= len(self.data):
            raise TdfError("unexpected end of data")
        b = self.data[self.pos]
        self.pos += 1
        return b

    def _take(self, n: int) -> bytes:
        if self.pos + n > len(self.data):
            raise TdfError("unexpected end of data")
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def varint(self) -> int:
        b = self._byte()
        neg = bool(b & 0x40)
        result = b & 0x3F
        shift = 6
        while b & 0x80:
            b = self._byte()
            result |= (b & 0x7F) << shift
            shift += 7
        return -result if neg else result

    def _string(self) -> str:
        raw = self._take(self.varint())
        return raw.rstrip(b"\x00").decode("utf-8", errors="replace")

    def _value(self, ty: int) -> Any:
        if ty == VARINT:
            return self.varint()
        if ty == STRING:
            return self._string()
        if ty == BLOB:
            return self._take(self.varint())
        if ty == GROUP:
            return self._group()
        if ty == LIST:
            et = self._byte()
            n = self.varint()
            return TList(et, [self._value(et) for _ in range(n)])
        if ty == MAP:
            kt, vt = self._byte(), self._byte()
            n = self.varint()
            return TMap(kt, vt, [(self._value(kt), self._value(vt)) for _ in range(n)])
        if ty == UNION:
            key = self._byte()
            if key == UNION_UNSET:
                return Union(key, None)
            return Union(key, self.field())
        if ty == INTLIST:
            return [self.varint() for _ in range(self.varint())]
        if ty == OBJTYPE:
            return (self.varint(), self.varint())
        if ty == OBJID:
            return (self.varint(), self.varint(), self.varint())
        if ty == FLOAT:
            return struct.unpack(">f", self._take(4))[0]
        raise TdfError(f"unsupported TDF type {ty:#x} at offset {self.pos}")

    def _group(self) -> list[Field]:
        fields: list[Field] = []
        # Some Blaze versions prefix a group with 0x02 (base-class marker).
        if self.pos < len(self.data) and self.data[self.pos] == 0x02:
            self.pos += 1
        while True:
            if self.pos >= len(self.data):
                raise TdfError("group not terminated")
            if self.data[self.pos] == 0x00:
                self.pos += 1
                return fields
            fields.append(self.field())

    def field(self) -> Field:
        raw = self._take(4)
        tag, ty = decode_tag(raw[:3]), raw[3]
        return Field(tag, ty, self._value(ty))


def decode(body: bytes) -> list[Field]:
    """Decode a full packet body (a sequence of tagged fields)."""
    r = Reader(body)
    out = []
    while r.pos < len(body):
        out.append(r.field())
    return out


def decode_safe(body: bytes) -> tuple[list[Field], str | None]:
    """Decode as far as possible; return (fields, error) instead of raising."""
    r = Reader(body)
    out: list[Field] = []
    try:
        while r.pos < len(body):
            out.append(r.field())
        return out, None
    except TdfError as e:
        return out, f"{e} (decoded {r.pos}/{len(body)} bytes)"


def find(fields: list[Field], tag: str, default: Any = None) -> Any:
    for f in fields:
        if f.tag == tag:
            return f.value
    return default
