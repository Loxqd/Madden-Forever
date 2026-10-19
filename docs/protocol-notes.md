# Protocol notes

What we believe about Madden NFL 20 (PC) networking, and how sure we are.

Confidence tags:
- **[CONFIRMED-PUBLIC]**: documented in public source code for other EA Blaze games. Not yet checked on Madden 20.
- **[INFERRED]**: an educated guess from patterns in other EA titles.
- **[UNKNOWN]**: needs a live capture from a real Madden 20 client.
- **[CONFIRMED-BINARY]**: found as a string in the Madden 20 game files (see [madden20-findings.md](madden20-findings.md)). This shows the value exists, not exactly how it is used.

Nothing here is **[TESTED-LIVE]** yet, because there is no game install in Phase 0.

## 1. Connection flow (how Blaze games usually do it)

1. The game resolves an EA "redirector" host name and connects to it, usually over TLS. **[CONFIRMED-PUBLIC]** (BF3/BF4/ME3 emulators)
2. It sends `Redirector.getServerInstance` (component 5, command 1) with its service name (`NAME`), platform, and SDK version. **[CONFIRMED-PUBLIC]**
3. The redirector replies with the real Blaze server address: `ADDR` (a union) holding `VALU {HOST, IP, PORT}`, plus `SECU` (whether to use TLS) and `XDNS`. **[CONFIRMED-PUBLIC]** for older titles; field set **[UNKNOWN]** for Madden 20.
4. The game connects to that Blaze server and calls `Util.preAuth`, then an `Authentication` login, then `Util.postAuth`. After that come game-specific components. **[CONFIRMED-PUBLIC]**

## 2. Host names and ports

| What | Value | Confidence |
|---|---|---|
| Redirector host | `spring18.gosredirector.ea.com` | **[CONFIRMED-BINARY]**: string in `Madden20.exe` |
| Redirector port | 42230 | **[TESTED-LIVE]**: the game connected to 127.0.0.1:42230 on 2026-10-19 |
| Blaze service name | `madden-2020-pc` | **[CONFIRMED-BINARY]** |
| EA account / tokens | `accounts.ea.com` (`/connect/auth`, `/connect/token`, `/connect/tokeninfo`) | **[CONFIRMED-PUBLIC]** for the Madden companion app; game use **[UNKNOWN]** |
| Entitlements / personas | `gateway.ea.com/proxy/identity/...`. PC persona namespace is `cem_ea_id`; the entitlement tag is `ONLINE_ACCESS`. | Same as the row above |
| Telemetry, QoS, CDN content | Hosts not known | **[UNKNOWN]** |

The first Phase 1 task is to get the real list. Record every DNS lookup the game makes while it starts up.

## 3. Packet framing

**Fire2** (the default in `server/frame.py`) is a 16-byte big-endian header. **[CONFIRMED-PUBLIC]** for Mirror's Edge Catalyst (Frostbite, 2016); for Madden 20 it is **[INFERRED]**.

```
u32 payload_len | u16 metadata_len | u16 component | u16 command |
u24 msg_num | u8 (msg_type << 5) | u8 options | u8 reserved
then metadata bytes, then payload bytes
```

Message types: 0 = request, 1 = reply, 2 = notification, 3 = error reply, 4 = ping, 5 = ping reply.

**Fire** is the older 12-byte header used by ME3 and BF3. It is kept as a fallback (`"framing": "fire"` in the config).

## 4. TDF body encoding **[CONFIRMED-PUBLIC]**

Every field is a 3-byte tag, a 1-byte type, then the value.

- **Tag:** up to 4 characters. Each character becomes `(c - 0x20) & 0x3F`, and the four 6-bit values are packed into 24 bits.
- **Types:**

  | Id | Type |
  |---|---|
  | 0 | varint |
  | 1 | string |
  | 2 | blob |
  | 3 | group (ends with byte 0x00) |
  | 4 | list |
  | 5 | map |
  | 6 | union (key byte, 0x7F means unset) |
  | 7 | int list |
  | 8 | object type |
  | 9 | object id |
  | 10 | float |
  | 12 | generic |

- **Varint:** the first byte holds 0x80 (continue), 0x40 (negative sign) and 6 value bits. Each later byte holds 0x80 (continue) and 7 value bits.
- **Strings:** a varint length (which counts the NUL), then UTF-8 bytes, then the NUL.

Source: the MIT-licensed `tdf` crate (jacobtread). We reimplemented it in Python from the format description; no code was copied.

## 5. Components

| Id | Name | Notes |
|---|---|---|
| 0 | KeepAlive | |
| 1 | Authentication | `login` = 10 (Mirror's Edge Catalyst), `originLogin` = 0x98 (ME3). Which one Madden 20 uses is **[UNKNOWN]**. |
| 4 | GameManager | Matchmaking and game sessions. Needed for head-to-head. |
| 5 | Redirector | |
| 7 | Stats | |
| 9 | Util | preAuth 7, postAuth 8, ping 2, fetchClientConfig 1 |
| 25 | AssociationLists | Friends and blocked lists |
| 28 | GameReporting | End-of-game results |
| 0x7802 | UserSessions | |
| 2060 | careermode | Madden custom component, from snallabot (Madden 22–26 companion app) |
| ? | Mut (Ultimate Team) | Component `Blaze::Mut`, with 154 request types including the `Dc` draft/events sub-area. The names are **[CONFIRMED-BINARY]** (full list in [madden20-findings.md](madden20-findings.md)). The id is **[UNKNOWN]**. |

## 6. TLS

EA games use DirtySDK "ProtoSSL", which carries its own built-in list of trusted EA certificate authorities. It ignores the Windows certificate store, so trusting our own certificate on the PC does not help.

- An old ProtoSSL bug let forged certificates through. It is confirmed for BF3/BF4 (Aim4kill/Bug_OldProtoSSL) and fixed in newer DirtySDK. Madden 20's ProtoSSL supports TLS 1.3, so it is a modern build that almost certainly has the fix. **[CONFIRMED-BINARY]** for TLS 1.3 support.
- The EA roots built into Madden 20 are "GOS 2013 Certificate Authority" and "GOS 2015 Certificate Authority". The game also has DirtyCert, which can fetch CA certificates from `gosca.ea.com` and from the redirector. **[CONFIRMED-BINARY]**
- The server logs `client is speaking TLS on a plain listener!` when a TLS ClientHello arrives on a plain port. That is the signal we need from the first live test.
- **Live result, 2026-10-19 [TESTED-LIVE]:** the game opens the redirector connection with TLS. Details of its ClientHello:
  - TLS 1.2. The record and client version are both 0x0303, and there is no supported_versions extension.
  - SNI is `spring18.gosredirector.ea.com`.
  - Cipher suites offered: ECDHE-ECDSA/RSA with AES-GCM or ChaCha20, plain RSA with AES-GCM/CBC, and SHA1/SHA256 CBC variants.
  - Groups: P-256 and P-384.
  - It retries once after about 20 s, then shows "lost connection with EA servers".
- Our plain listener can't answer, so `redirector.tls = true` with a self-signed certificate (`tools/make_test_cert.py`) is the next test. The server logs the alert the game sends back (for example `TLSV1_ALERT_UNKNOWN_CA`).
- **Self-signed certificate result [TESTED-LIVE]:** the game receives ServerHello, Certificate, ServerKeyExchange and ServerHelloDone, then closes the TCP connection. It sends no ClientKeyExchange and **no alert**; ProtoSSL just drops the connection. Certificate validation is enforced.

## 7. Message signing

The Madden companion app (Madden 22+) signs each Blaze request with a `MessageAuth` blob, built from static keys, MD5 and XOR, per snallabot. Whether the Madden 20 PC client does anything similar on its Blaze socket is **[UNKNOWN]**. A server that does not check it can simply ignore it.
