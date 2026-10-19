# Madden Forever

A private server project to bring back **Madden NFL 20 (PC) Ultimate Team** online. EA shut down the official servers on 15 April 2024.

**Status:** Phase 0. Research is done and a Blaze server skeleton runs locally. **No game client has connected yet.** Before buying the game, read [docs/feasibility.md](docs/feasibility.md).

## What works

| Piece | State |
|---|---|
| TDF encoder/decoder, Fire2 and Fire framing | Done, unit tested |
| Redirector (`getServerInstance`) pointing at our Blaze port | Done, tested with the fake client only |
| Util preAuth/ping/postAuth/fetchClientConfig, login accepting any token | Placeholder replies, tested with the fake client only |
| Packet capture log (hex + decoded JSON) and TLS-hello detection | Done |
| One-click start/stop | Done |
| Anything Madden-specific (menus, Ultimate Team, head-to-head) | Not started |

## Running it

Requirements: Windows and Python 3.10 or newer. No other packages are needed.

- **Start:** double-click `start.bat`. On first run it creates `config\server.json`.
- **Stop:** double-click `stop.bat`.
- **Watch the game's connections:** double-click `watch.bat` before starting Madden. It shows which ports the game uses.
- **Self-test** (with the server running): `py -3 tools\fake_client.py`
- **Unit tests:** `py -3 -m unittest discover -s tests`

The server listens on `127.0.0.1` only. Defaults are the redirector on 42230 and Blaze on 10041; both are set in `config\server.json`.

- **Server output:** `logs\server-*.log`
- **Every packet:** `logs\capture-*.jsonl`

## Layout

```
server/        the Blaze server (python -m server)
  tdf.py       TDF body encoding
  frame.py     packet headers (fire2 default, fire fallback)
  components.py  component/command names + handlers
  core.py      listeners, sessions, capture log, account store
config/        server.example.json (copied to server.json)
scripts/       start.ps1 / stop.ps1 (called by the .bat files)
tools/         fake_client.py: pretends to be the game
tests/         offline unit tests
docs/          feasibility report, protocol notes (with confidence tags), progress log
```

## Ground rules

These follow the approach of Rebound-2k21:

- We do not modify game files on disk, and we do not bypass EA app, Origin or Denuvo ownership checks.
- We do not include or distribute EA code, assets or data.
- The project is noncommercial.
- Claims are tagged by how sure we are: see [docs/protocol-notes.md](docs/protocol-notes.md).

## Credits / prior art

- Protocol knowledge comes from public projects. The `tdf` crate and Pocket Relay are by jacobtread (MIT); snallabot is MIT.
- No code was copied. This is a fresh Python implementation.
- The project's own license is not chosen yet.
