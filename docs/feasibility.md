# Madden Forever: feasibility report (Phase 0)

*Written 19 October 2026, before any game install. Everything about Madden 20 itself is unconfirmed until we test it with a real copy.*

## The short answer

- **Is it possible?** Probably, but it is unproven, and one early test decides it.
- **Getting the game to sign in and reach the main menu on our server:** hard. It is a few weeks to months of work, but only if the encryption problem (below) is solvable.
- **Getting Ultimate Team back with cards, packs, solos and head-to-head:** very hard. EA's servers ran almost all of Ultimate Team, so we would rebuild nearly all of it ourselves. Plan on many months.
- **Overall difficulty: 8 out of 10.** For comparison, a Mass Effect 3 server with existing open-source help is about 4/10.
- **Advice:** don't commit to the full project yet. If you can get a legitimate copy cheaply, the first test (one evening) tells us whether the project is realistic.

## Update, 19 Oct 2026: after scanning the game files

Details are in [madden20-findings.md](madden20-findings.md).

- **Good news:** the server names are now known. The service is `madden-2020-pc` (the guess was right) and the redirector is `spring18.gosredirector.ea.com`.
- **Good news:** the game names all ~150 Ultimate Team requests (open pack, auction bid, lineups, solos, Draft Champions…). We know exactly what we would have to answer, so it is no longer guesswork.
- **Bad news:** the game's encryption code is a modern version (it supports TLS 1.3) and trusts only EA's own "GOS 2013/2015" certificate authorities. The old certificate trick is off the table. Encryption is still the deciding risk; the live test below settles it.
- **Copy protection:** the owner's copy runs with a third-party launcher patch, because the EA app no longer launches it. The project itself must not depend on, or ship, that patch.

## Update, 19 Oct 2026: go/no-go result

- **The game reaches our server.** With one hosts-file line, Madden 20 connects to our redirector on port 42230.
- **It refuses our certificate.** It opens TLS 1.2, receives our certificate, and hangs up straight away. Risk 1 is now confirmed: an unmodified game will not talk to us.
- **What's left:**
  - **(a)** ~~A long shot that needs no game changes: the game's "DirtyCert" feature, which can fetch missing CA certificates.~~ **Ruled out the same day.** DirtyCert fetches through `gosca.ea.com:44125`, which is protected by EA's own certificate, so we can't stand in for it.
  - **(b)** An optional patch, applied while the game runs, that makes the certificate check accept our server, like Rebound's optional `patch_memory`. This changes nothing on disk and does not touch ownership checks, but it is a change to the game's behaviour, and Denuvo on retail copies makes it fragile.
  - **(c)** Stop here.

## What Madden 20 needs from a server

When Madden 20 goes online, it does roughly this:

1. It asks EA's **redirector** (`gosredirector.ea.com`) where the game server is.
2. It connects to that **Blaze server**, EA's own game backend, and signs in with a token from the EA app (formerly Origin).
3. It loads its settings, then talks to Madden-specific services: Ultimate Team, matchmaking, stats, and so on.

EA shut all of this down on **15 April 2024**. Our job is to stand in for every one of those servers.

## What other people have already solved

Fans have done this kind of work before for other EA games. Blaze is the same system EA used across Battlefield, Mass Effect, FIFA, Madden and others.

| Project | Game | License | What it gives us |
|---|---|---|---|
| [Pocket Relay](https://github.com/PocketRelay/Server) | Mass Effect 3 | MIT | A complete, working Blaze server. Proof that this kind of project can be finished. |
| [`tdf` crate / BlazePK](https://github.com/jacobtread/tdf) | ME3 / BF3 | MIT | Exact details of how Blaze packs data. We built our decoder from this. |
| [grid-leak/blaze](https://github.com/grid-leak/blaze) | Mirror's Edge Catalyst (Frostbite, 2016) | AGPL-3.0 | The newer packet header that Madden 20 probably uses, plus login, settings and friends lists. |
| [Frostbite-3](https://github.com/ByxkDev/Frostbite-3) | Battlefield 4 (PS3) | GPL-3.0 | Redirector, login, matchmaking and stats working without changing the game, through DNS redirection. |
| [New-Blaze-Emulator](https://github.com/Tratos/New-Blaze-Emulator), [squaredx/blaze-server](https://github.com/squaredx/blaze-server) | Battlefield 3 | GPL-2.0 | Older, full Blaze emulators to learn from. |
| [Aim4kill/Bug_OldProtoSSL](https://github.com/Aim4kill/Bug_OldProtoSSL) | BF3 / BF4 | not stated | A trick that made old EA games accept a fake security certificate. Fixed in newer games. |
| [snallabot](https://github.com/snallabot/snallabot-service) | Madden 22–26 companion app | MIT | The only real Madden Blaze details we found: how EA sign-in works, the service names, and the custom "careermode" component. |

**About the licenses:** MIT code can be reused if we give credit. Copying code from the GPL or AGPL projects would force our project to use the same license. Reading them to learn how the protocol works is fine. Our code is written fresh, in Python.

**What we did not find:** any public Madden 20 private server, any captured Madden 20 traffic, or any public description of how Ultimate Team talks to the server. For Madden specifically, we would be the first.

## What this repo already does

There is a working server skeleton you can start and stop with one click:

- It reads and writes Blaze's data format. All 12 data types are covered and tested.
- It answers the redirector, the first login steps, and pings.
- It accepts any sign-in token, so it does not need EA.
- It logs every packet so we can study the real game later.
- It recognises when the game tries to use encryption. That is the key signal for the first test.

It has only been tested against a fake client written to act like the game. None of it is tested against the real Madden 20.

## What we would have to build ourselves

Roughly in order, with a rough size for each:

1. **Getting the game to connect at all.** Point EA's host names at our server, using a hosts-file entry or local DNS, and get past the encryption. *Unknown size: this is the make-or-break step.*
2. **Sign-in and the main menu.** Fill in the real replies to the settings and login calls. We learn their shape from the capture logs, one error at a time. *Weeks.*
3. **EA account web services.** The game or the EA app may call `accounts.ea.com` and `gateway.ea.com` over HTTPS to check tokens and ownership. If so, those would need stand-ins too. *Small to medium, if the encryption problem is solved.*
4. **Ultimate Team.** This is the hard part. EA's servers held almost everything:
   - **Card catalog.** Every player item, with ratings, program (TOTW, Team Diamonds, Legends…), image references and upgrade rules. EA updated this weekly, from the server. The game install probably contains player models and some artwork, but probably not the full catalog of cards that were ever released. We would have to rebuild it, either from community databases (sites like MUT.GG, or archives of old ones) or by designing our own cards. That brings up copyright and terms-of-service questions.
   - **Packs and store.** Pack definitions, drop odds, coins, Training points and the store front. Easy to invent, hard to make match the original.
   - **Collection and lineups.** Each player's cards, lineup, team chemistry, and sets (trade in X cards to get Y).
   - **Solos and challenges.** Each challenge is a game setup with rules and rewards, sent by the server. Those definitions are gone. We would author new ones, or recover them if the game files hold any.
   - **Auction house.** A player-to-player market. Only worth building once there are real players.
   - **Head-to-head and seasons.** Matchmaking, plus whatever connects two players' games. Some EA sports titles run that peer-to-peer and some through EA relays; for Madden 20 we don't know. Results and rankings also go through the server.
   - *Size: many months.* The work isn't technically harder than steps 1–3, but there is a lot of it, and every piece has to be reverse-engineered from the game's messages.
5. **Running it for other people.** A hosted server, accounts, and a simple installer for the hosts entry and any certificate. This is similar to what Rebound does with its VPS setup. *Weeks.*

## The biggest risks

1. **Encryption, the main blocker.** EA's games check the server's security certificate against a list built into the game, and they ignore Windows' own list. The known trick for faking a certificate only works on older games such as BF3 and BF4. Madden 20 is from 2019, so it probably has the fix. If the game insists on a real EA certificate, the only way forward is to change the game's behaviour while it runs (an in-memory patch), and that runs straight into risk 2. There is one hopeful sign: some newer emulators (grid-leak) talk to the game without encryption after the first step. If Madden 20 does that too, only the redirector connection matters.
2. **Denuvo and EA app copy protection.** Reports say Madden 20 PC ships with **Denuvo Anti-Tamper** and needs the **EA app** (formerly Origin) to run. We did not find any anti-cheat; nothing suggests EasyAntiCheat or EA Javelin. Denuvo does not block redirecting network traffic. It does make patching the game's code, on disk or in memory, fragile, and that is legally sensitive. Our rule, carried over from Rebound, is to never bypass ownership checks or modify game files.
3. **Getting a legitimate copy.** Madden 20 PC seems to no longer be sold. We could not confirm whether it was delisted. A second-hand key may already be used, and the EA app must still let the game launch for an owned copy. **Check this before paying anything.**
4. **Lost content.** Most of what made Ultimate Team Ultimate Team (the cards and the challenges) lived on EA's servers and may simply be gone. Even if the technology works, a revival may need new, fan-made content.
5. **Legal and EA terms.** Running unofficial servers breaks EA's terms of service. Getting around copy protection (risk 2) is a separate, more serious legal issue. Distributing EA's data (card images, the original catalog) is a copyright issue. Keeping the project noncommercial, not shipping EA files, and not touching ownership checks keeps the risk down, but does not remove it. *This is not legal advice.*
6. **Size of the work.** This is a multi-month, mostly solo reverse-engineering project, with a working result not guaranteed.

## Difficulty ratings

| Goal | Rating | Notes |
|---|---|---|
| Game reaches our redirector | 2/10 | Hosts file plus capture log. We can tell in one evening. |
| Gets past encryption | **?/10** | Ranges from free (no check) to blocked (needs a code patch). This decides the whole project. |
| Sign-in to the main menu | 6/10 | If encryption is solved. Lots of trial and error. |
| Offline-style Ultimate Team (collection, packs, solos against the CPU) | 8/10 | Mostly content work and a lot of message decoding. |
| Head-to-head and auction house | 9/10 | Depends on how matches connect players; needs real players to test. |
| **Overall** | **8/10** | |

## Go / no-go test (Phase 1, the first thing to do with a copy)

1. As administrator, add this line to `C:\Windows\System32\drivers\etc\hosts`:
   `127.0.0.1 spring18.gosredirector.ea.com`
   Delete the line again when you are done testing.
2. Run `start.bat`, then `watch.bat`.
3. Start the game and choose Ultimate Team. `watch.bat` prints every address and port the game connects to. A connection to `127.0.0.1:<port>` is the redirector. If that port is not 42230, put the real port in `config\server.json` (`redirector.port`), then run `stop.bat` and `start.bat` and try again.
4. Leave the game at its error screen, then run `stop.bat`.
5. Read `logs/server-*.log`:
   - **Readable packets (`-> Redirector.getServerInstance`):** no encryption on that port. Excellent news; continue with sign-in.
   - **`client is speaking TLS on a plain listener!`:** the game wants encryption. Next, see whether it accepts a self-made certificate (TLS mode in the config). If it does not, we are at risk 1, and it's time to decide whether to go on.
   - **Nothing at all:** wrong host name or port. Repeat step 3.

**If the game gets past step 5, the project is realistic. If it is blocked at encryption with no clean way around it, stopping there is a reasonable call.**

## Sources

- EA Blaze/TDF format: [jacobtread/tdf](https://github.com/jacobtread/tdf), [docs.rs blaze-pk](https://docs.rs/blaze-pk/)
- Fire2 header: [grid-leak/blaze `src/packet.rs`](https://github.com/grid-leak/blaze)
- BF4 redirector, ports and TLS notes: [ByxkDev/Frostbite-3](https://github.com/ByxkDev/Frostbite-3)
- ProtoSSL certificate bug: [Aim4kill/Bug_OldProtoSSL](https://github.com/Aim4kill/Bug_OldProtoSSL)
- Madden Blaze sign-in, service names and MessageAuth: [snallabot EA API notes](https://github.com/snallabot/snallabot-service/blob/main/docs/madden/ea_api.md), [author's write-up](https://nallapareddy.com/snallabot-post/)
- Shutdown date (15 April 2024): [TrueAchievements](https://www.trueachievements.com/news/ea-server-closures-2024), [Deku Deals](https://www.dekudeals.com/items/madden-nfl-20-500-madden-ultimate-team-points)
- Denuvo and EA app requirement: [PCGamingWiki](https://www.pcgamingwiki.com/wiki/Madden_NFL_20) (read through a search summary; the page itself was blocked to us), [CrackWatcher](https://crackwatcher.com/game/madden-nfl-20)
- Rebound-2k21 working style: [Loxqd/Rebound-2k21](https://github.com/Loxqd/Rebound-2k21)
