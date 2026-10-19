"""Blaze component ids and the handlers we have so far.

Component/command ids for the core components come from public emulators
(Pocket Relay / ME3, grid-leak / Mirror's Edge Catalyst, Frostbite-3 / BF4).
Response layouts are best guesses from those projects. NOTHING in this file
has been checked against a Madden NFL 20 client yet - the capture log is how
we will find out what the game really sends and expects.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Callable

from . import tdf
from .frame import Packet
from .tdf import Writer

if TYPE_CHECKING:
    from .core import Session

COMPONENTS = {
    0x0000: "KeepAlive",
    0x0001: "Authentication",
    0x0004: "GameManager",
    0x0005: "Redirector",
    0x0007: "Stats",
    0x0009: "Util",
    0x000A: "CensusData",
    0x000B: "Clubs",
    0x000F: "Messaging",
    0x0019: "AssociationLists",
    0x001C: "GameReporting",
    0x7802: "UserSessions",
    # Ids >= 0x0800 are game-specific ("custom") components. The Madden
    # companion app talks to 2060 = "careermode" (from snallabot's notes).
    # Ultimate Team almost certainly lives in another custom component.
    2060: "careermode (Madden custom)",
}

COMMANDS = {
    (0x0001, 0x000A): "login",
    (0x0001, 0x001D): "listEntitlements",
    (0x0001, 0x0030): "logout",
    (0x0001, 0x0098): "originLogin",
    (0x0005, 0x0001): "getServerInstance",
    (0x0009, 0x0001): "fetchClientConfig",
    (0x0009, 0x0002): "ping",
    (0x0009, 0x0007): "preAuth",
    (0x0009, 0x0008): "postAuth",
    (0x0009, 0x0016): "setClientMetrics",
    (0x0009, 0x001C): "setClientState",
    (0x0019, 0x0006): "getLists",
    (0x7802, 0x0014): "updateNetworkInfo",
}


def component_name(c: int) -> str:
    if c in COMPONENTS:
        return COMPONENTS[c]
    return f"custom_{c}" if c >= 0x800 else f"comp_{c:#06x}"


def command_name(c: int, cmd: int) -> str:
    return COMMANDS.get((c, cmd), f"cmd_{cmd:#06x}")


Handler = Callable[["Session", Packet, list], "Packet | list[Packet] | None"]
HANDLERS: dict[tuple[int, int], Handler] = {}


def handles(component: int, command: int):
    def wrap(fn: Handler) -> Handler:
        HANDLERS[(component, command)] = fn
        return fn
    return wrap


# --------------------------------------------------------------------------
# Redirector - the first thing the game talks to. It asks "where is the Blaze
# server for service NAME?" and we answer with our own address.

@handles(0x0005, 0x0001)
def get_server_instance(s: "Session", p: Packet, req: list) -> Packet:
    name = tdf.find(req, "NAME", "?")
    s.log(f"redirector: client asked for service {name!r}")
    cfg = s.server.cfg
    addr = Writer().str("HOST", cfg["public_host"]).int("IP", _ip_to_int(cfg["public_host"])) \
                   .int("PORT", cfg["blaze"]["port"])
    body = Writer().union_group("ADDR", 0, "VALU", addr) \
                   .int("SECU", 1 if cfg["blaze"].get("tls") else 0) \
                   .int("XDNS", 0)
    return p.reply(body.bytes())


def _ip_to_int(host: str) -> int:
    try:
        a, b, c, d = (int(x) for x in host.split("."))
        return (a << 24) | (b << 16) | (c << 8) | d
    except ValueError:
        return 0


# --------------------------------------------------------------------------
# Util

@handles(0x0009, 0x0007)
def pre_auth(s: "Session", p: Packet, req: list) -> Packet:
    cfg = s.server.cfg
    conf = Writer().map_str_str("CONF", {
        "pingPeriod": "15s",
        "voipHeadsetUpdateRate": "1000",
        "xlspConnectionIdleTimeout": "300",
    })
    body = Writer() \
        .int("ANON", 0) \
        .str("ASRC", "000000") \
        .list_int("CIDS", sorted(c for c in COMPONENTS if c)) \
        .group("CONF", conf) \
        .str("INST", cfg["service_name"]) \
        .int("MINR", 0) \
        .str("NASP", "cem_ea_id") \
        .str("PLAT", "pc") \
        .str("PTAG", "") \
        .str("RSRC", "000000") \
        .str("SVER", "Madden Forever (skeleton)")
    return p.reply(body.bytes())


@handles(0x0009, 0x0002)
def ping(s: "Session", p: Packet, req: list) -> Packet:
    return p.reply(Writer().int("STIM", int(time.time())).bytes())


@handles(0x0009, 0x0001)
def fetch_client_config(s: "Session", p: Packet, req: list) -> Packet:
    cfid = tdf.find(req, "CFID", "")
    s.log(f"util: client wants config section {cfid!r}")
    return p.reply(Writer().map_str_str("CONF", {}).bytes())


@handles(0x0009, 0x0008)
def post_auth(s: "Session", p: Packet, req: list) -> Packet:
    return p.reply(b"")


# --------------------------------------------------------------------------
# Authentication. On real servers the client sends an EA/Origin token and the
# server checks it with EA. EA's side is gone, so we accept any token and map
# it to a local account. (Which login command Madden 20 uses is unknown.)

def _login(s: "Session", p: Packet, req: list) -> Packet:
    token = tdf.find(req, "AUTH") or tdf.find(req, "TOKN") or ""
    user = s.server.accounts.get_or_create(str(token))
    s.user = user
    s.log(f"auth: logged in {user['name']} (id {user['id']})")
    persona = Writer().str("DSNM", user["name"]).int("LAST", int(time.time())) \
                      .int("PID", user["id"]).int("STAS", 0).int("XREF", 0).int("XTYP", 0)
    sess = Writer().int("BUID", user["id"]).int("FRST", 0).str("KEY", s.session_key) \
                   .int("LLOG", int(time.time())).str("MAIL", "") \
                   .group("PDTL", persona).int("UID", user["id"])
    return p.reply(Writer().group("SESS", sess).bytes())


HANDLERS[(0x0001, 0x000A)] = _login
HANDLERS[(0x0001, 0x0098)] = _login


@handles(0x0001, 0x001D)
def list_entitlements(s: "Session", p: Packet, req: list) -> Packet:
    return p.reply(Writer().list_group("NLST", []).bytes())


# --------------------------------------------------------------------------
# Keep-alive (component 0, command 0) - just echo an empty reply.

@handles(0x0000, 0x0000)
def keep_alive(s: "Session", p: Packet, req: list) -> Packet:
    return p.reply(b"")
