# Progress log

Each run records what was done and whether it was tested. "Tested live" means it was tested against a real Madden NFL 20 client.

## 2026-10-19: Phase 0 (no game install)

**Research**

- Collected public Blaze knowledge and fan server projects, with their licenses.
- Gathered what is known about Madden sign-in (from snallabot) and Madden 20 protection.
- Results: `docs/feasibility.md` and `docs/protocol-notes.md`.

**Server skeleton (Python 3, standard library only)**

- `server/tdf.py`: full TDF encoder and decoder.
- `server/frame.py`: Fire2 and Fire packet framing.
- `server/components.py`: handlers for:
  - `Redirector.getServerInstance`
  - `Util.preAuth`, `ping`, `fetchClientConfig`, `postAuth`
  - `Authentication.login` and `originLogin` (accepts any token and creates a local account)
  - `listEntitlements`
  - keep-alive
- Unknown commands are logged and get an empty reply.
- Every packet is logged to `logs/capture-*.jsonl`, both as hex and decoded.
- A TLS ClientHello arriving on a plain port is detected and logged.
- `start.bat` and `stop.bat` start and stop the server in the background, with a PID file, a port check, and a guard against starting it twice.

**Tested (offline only)**

- `python -m unittest discover -s tests`: 9 tests pass.
- `tools/fake_client.py` against the running server: the full flow passes (redirector → Blaze → preAuth → login → ping → unknown custom command → Fire ping).
- `start.bat` → fake client → `start.bat` again (refused, already running) → `stop.bat` → `stop.bat` again ("not running"). Ports close after stop.

**Not tested live: everything.** No Madden 20 client has connected yet.

**Next (Phase 1, needs the game):** see the "Go / no-go test" section in `docs/feasibility.md`.

## 2026-10-19: static scan of the game files (read-only)

- Scanned strings in `Madden20.exe` and `EAWebKit.dll`. Nothing was run and nothing was modified. Results are in `docs/madden20-findings.md`.
- Confirmed the service name `madden-2020-pc` and the redirector `spring18.gosredirector.ea.com`.
- ProtoSSL supports TLS 1.3 and trusts the EA roots "GOS 2013" and "GOS 2015", so the old cert bug is ruled out.
- Listed the 154 `Blaze::Mut` request types, our Ultimate Team checklist.
- Added `watch.bat` / `tools/watch-connections.ps1` to print every connection the game opens (this is how we learn the redirector port).
- The install runs with a third-party launcher patch (OrangeEmu). The project must not depend on it or ship it.
- **Not tested live:** still nothing. The go/no-go test is next.

## 2026-10-19: go/no-go test, first live contact

- **First try:** the game said "servers down". The hosts entry hadn't been saved, so the game asked EA's real (dead) redirector.
- **Second try:** with `127.0.0.1 spring18.gosredirector.ea.com` in the hosts file, **the game connected to our redirector on port 42230**. **[TESTED-LIVE]**
- It opened with a TLS 1.2 ClientHello. Our plain listener couldn't reply, so after about 20 s and one retry the game showed "lost connection with EA servers". The ClientHello details are in `protocol-notes.md` §6.
- Added TLS mode: the handshake now runs inside the session, so a rejected certificate is logged with the client's alert. Also added `tools/make_test_cert.py` (self-signed cert for the redirector host) and a `--tls` option for `fake_client.py`.
  - Tested locally: a lenient client completes the whole flow over TLS 1.3, and a strict client is rejected and logged as `TLSV1_ALERT_UNKNOWN_CA`.
- Fixed `start.ps1`: it recorded conhost's PID instead of python's.
- **Next:** run the game against TLS mode and read which alert it sends.

## 2026-10-19: TLS mode, first game run

- **The game connected over TLS to our self-signed redirector three times in about 15 s.** Each time it dropped the TCP connection within about a second of the handshake starting. It sent **no TLS alert** (the server saw WinError 64 / connection reset). **[TESTED-LIVE]**
- We can't yet say whether that is a certificate rejection or something else in the handshake. So the server now drives TLS by hand (`ssl.MemoryBIO`) and logs every TLS record the client sends, plus a one-line verdict:
  - "hung up right after our certificate" points to a rejected certificate.
  - "ClientKeyExchange seen" means the certificate was accepted.
  - Tested locally with a lenient client (full flow) and a strict client (logged as `ALERT fatal unknown_ca`).
- **Next:** run the game once more and read the record trail.

## 2026-10-19: result, the certificate is rejected **[TESTED-LIVE]**

The game made four attempts (06:26:45, :56, 06:27:00, :04), and every one went the same way:

1. Client sends ClientHello.
2. We send ServerHello + Certificate + ServerKeyExchange + ServerHelloDone, negotiating TLS 1.2.
3. The client closes the TCP connection at once. It sends no ClientKeyExchange and no alert.

So version, cipher and SNI all match, and **the game refuses our certificate**.

## 2026-10-19: DirtyCert route, a dead end

The full write-up is in `madden20-findings.md` → "DirtyCert investigation". In short:

- The CA-fetch service `gosca.ea.com:44125` is still live, but it is TLS with a certificate signed by EA's "GOS 2011" CA. We can't impersonate it, and the real service only hands out EA's own CAs.
- No route without changing the game was found. That leaves option (b), the optional runtime patch, or (c), stopping. This is the "blocked at encryption" outcome from the feasibility report. An unmodified game will not talk to a server whose certificate isn't signed by EA's GOS 2013/2015 CA.
