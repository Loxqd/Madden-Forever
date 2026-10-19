"""Offline tests: python -m unittest discover -s tests"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import tdf  # noqa: E402
from server.frame import Fire, Fire2, Packet, REPLY  # noqa: E402
from server.tdf import Writer  # noqa: E402


class TagTests(unittest.TestCase):
    def test_round_trip(self):
        for tag in ["ADDR", "HOST", "IP", "PORT", "CIDS", "SESS", "PDTL", "DSNM", "A1B2", "X"]:
            self.assertEqual(tdf.decode_tag(tdf.encode_tag(tag)), tag)

    def test_matches_six_bit_packing(self):
        # Independent formulation: each char becomes (c - 0x20) & 0x3F, packed into 24 bits.
        for tag in ["ADDR", "VALU", "CIDS", "IP", "ERRC"]:
            v = 0
            for i, c in enumerate(tag.ljust(4, " ")):
                v |= ((ord(c) - 0x20) & 0x3F) << (18 - 6 * i)
            self.assertEqual(tdf.encode_tag(tag), v.to_bytes(3, "big"), tag)


class VarIntTests(unittest.TestCase):
    def test_values(self):
        for v in [0, 1, 63, 64, 127, 128, 8191, 2**31, 2**63 - 1, -1, -64, -100000]:
            self.assertEqual(tdf.Reader(tdf.encode_varint(v)).varint(), v, v)

    def test_single_byte_small(self):
        self.assertEqual(tdf.encode_varint(5), b"\x05")
        self.assertEqual(tdf.encode_varint(64), b"\x80\x01")


class BodyTests(unittest.TestCase):
    def test_everything_round_trips(self):
        inner = Writer().str("HOST", "127.0.0.1").int("PORT", 10041)
        body = (Writer().int("ERRC", 0).str("NAME", "madden-2020-pc").blob("BLOB", b"\x00\xff")
                .group("GRP", inner).list_int("CIDS", [1, 4, 9]).list_str("STRS", ["a", "b"])
                .list_group("LGRP", [inner, inner]).map_str_str("CONF", {"k": "v"})
                .map_str_int("MAPI", {"x": -5}).union_group("ADDR", 0, "VALU", inner)
                .union_unset("NONE").intlist("ILST", [7, 8]).objtype("OTYP", 4, 1)
                .objid("OBID", 4, 1, 99).float("FLT", 1.5)).bytes()
        f = tdf.decode(body)
        self.assertEqual(tdf.find(f, "NAME"), "madden-2020-pc")
        self.assertEqual(tdf.find(tdf.find(f, "GRP"), "PORT"), 10041)
        self.assertEqual(tdf.find(f, "CIDS").items, [1, 4, 9])
        self.assertEqual(tdf.find(f, "CONF").items, [("k", "v")])
        self.assertEqual(tdf.find(f, "MAPI").items, [("x", -5)])
        self.assertEqual(tdf.find(tdf.find(f, "ADDR").field.value, "HOST"), "127.0.0.1")
        self.assertIsNone(tdf.find(f, "NONE").field)
        self.assertEqual(tdf.find(f, "OBID"), (4, 1, 99))
        self.assertEqual(tdf.find(f, "FLT"), 1.5)

    def test_decode_safe_reports_truncation(self):
        body = Writer().str("NAME", "hello").bytes()[:-2]
        fields, err = tdf.decode_safe(body)
        self.assertEqual(fields, [])
        self.assertIn("end of data", err)


class FrameTests(unittest.TestCase):
    def check(self, framing, body_len):
        p = Packet(9, 7, REPLY, 0x123, 0, b"x" * body_len)
        buf = bytearray(framing.write(p) + b"extra")
        out = framing.try_read(buf)
        self.assertEqual((out.component, out.command, out.msg_type, out.body), (9, 7, REPLY, p.body))
        self.assertEqual(buf, bytearray(b"extra"))

    def test_fire2(self):
        self.check(Fire2, 10)
        self.assertEqual(len(Fire2.write(Packet(1, 1))), 16)

    def test_fire_small_and_jumbo(self):
        self.check(Fire, 10)
        self.check(Fire, 70000)

    def test_partial_returns_none(self):
        data = Fire2.write(Packet(1, 1, body=b"abc"))
        self.assertIsNone(Fire2.try_read(bytearray(data[:-1])))


if __name__ == "__main__":
    unittest.main()
