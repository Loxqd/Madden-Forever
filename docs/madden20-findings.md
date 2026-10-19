# Madden NFL 20 (PC): what the game files tell us

*19 October 2026. Read-only string scan of `Madden20.exe` and `EAWebKit.dll`. Nothing was run, and no game files were changed or copied into this repo.*

**About this install.** The copy used here is the owner's Origin download, run with a third-party launcher patch (OrangeEmu) because it no longer launches through the EA app. This project does not ship, require or link to that patch. The server has to work with an unmodified client launched through the EA app.

## Build

- Built 2019-08-14 from Frostbite release `2018.0` (changelist 3427598), branch `MaddenData`. Source: `Info_Win64_retail.BuildSettings`.
- Contains BlazeSDK and DirtySDK. The source paths mention `e:\mad\tnt\code\external\ea\blazesdk\...`.

## Confirmed from the binary

| What | Value | Phase 0 guess |
|---|---|---|
| Blaze service name | `madden-2020-pc` (also `madden-2020-pc-trial`) | Correct |
| Production redirector | `spring18.gosredirector.ea.com` | Unknown before |
| Test redirectors | `spring18.gosredirector.{sdev,scert,stest}.ea.com` | n/a |
| EA account web services | `accounts.ea.com`, `signin.ea.com`, `gateway.ea.com`, plus `.int.` variants | Confirmed present |
| Telemetry | `pin-river.data.ea.com` | n/a |
| CA fetch service | `gosca.ea.com` (DirtyCert) | n/a |
| Embedded web browser | EAWebKit (used for store and web pages) | n/a |

The redirector **port** is not stored as text. 42230 remains the guess, and the live test will show the real one.

## TLS (the main risk)

- ProtoSSL in this build supports **TLS 1.3**: we found `tls13`, `c hs traffic` and other TLS 1.3 key-schedule labels. That makes it a modern DirtySDK, so the old BF3/BF4 forged-certificate bug almost certainly does not apply.
- The game has two EA root CAs built in: **"GOS 2013 Certificate Authority"** and **"GOS 2015 Certificate Authority"** (Electronic Arts, Global Online Studio). We cannot sign certificates with them.
- It also carries public roots (Baltimore CyberTrust, GlobalSign, Amazon), probably for HTTPS and EAWebKit.
- **DirtyCert** can download missing CA certificates from `gosca.ea.com` and from the redirector (`Blaze::Redirector::CACertificateRequest`). Whether those downloads are themselves verified is **[UNKNOWN]**. It is worth studying, but don't count on it.
- BlazeSDK accepts server-side setting overrides named `Override_ProtoSSL_`, `Override_ProtoHttp_`, `Override_QosClient_` and others. These arrive after a connection already exists, so they cannot help with the first TLS handshake. They might relax the checks on later connections. **[UNKNOWN]**
- The redirector's `getServerInstance` reply carries a "secure" flag (`SECU`). If the main Blaze connection can be told to use plain TCP, only the redirector connection needs a certificate the game accepts.

## DirtyCert investigation (19 Oct 2026)

Question: can DirtyCert, ProtoSSL's "fetch a missing CA" feature, be used to get the game to trust our certificate without changing the game?

**Answer: no.** The details:

- **Request format.** The strings in `Madden20.exe` are:
  - query parameters `?v=`, `&vers=`, `&name=`, `&host=`, `&port=`, `&bits=`, `&entr|CN=`, `&entr|O=`, `&entr|OU=`, `&entr|C=`, `&entr|L=`, `&entr|ST=`
  - a response path `cacertificate.certificatelist.certificatelist` with base64 certificates
  - redirector commands `getCACertificates` / `findCACertificates`

  So DirtyCert sends EA's CA service a description of the issuer it is missing, and gets a list of CA certificates back. **[CONFIRMED-BINARY]**
- **Where it goes.** `gosca.ea.com` sits in the ProtoSSL string table. It still resolves (159.153.51.21), and **port 44125 is still open on EA's side**. The rest of 80, 443, 42230 and 10443 were closed. **[TESTED-LIVE]**, by probing from this PC.
- **That connection is TLS too.** `openssl s_client` shows TLS 1.2 with a certificate for `CN=gosca.ea.com`, issued by **"GOS 2011 Certificate Authority"**, one of EA's own CAs. The client checks this connection against its built-in EA roots like any other, so we cannot pose as `gosca.ea.com` either. **[TESTED-LIVE]**
- **Even if we could, it wouldn't help.** The real `gosca` only hands out EA's own CAs, and none of those can sign a certificate for our server.
- **Background.** In the open-source 2010 ProtoSSL (BSD-licensed, shipped with EAWebKit; mirrored at kitsilanosoftware/DirtySDK and xebecnan/EAWebkit), `ProtoSSLSetCACert` accepts any *self-signed* CA. The `ncrt` control (`bAllowAnyCert`) turns certificate checking off entirely. Both are calls *inside* the game, not something a server can reach before the first TLS connection succeeds.
  - BlazeSDK's `Override_ProtoSSL_*` client-config keys could in principle set `ncrt` for *later* connections. They are delivered over the redirector/Blaze connection we can't establish, so it's a chicken-and-egg problem.

**Side finding:** EA's real `spring18.gosredirector.ea.com:42230` (159.153.51.20) still accepts connections. EA's shared redirector is alive, presumably answering "no matching instance" for the retired `madden-2020-pc` service.

## Blaze components the client knows about

These counts are type names found per component. More names suggest more server work.

| Component | Type names | Notes |
|---|---|---|
| FranchiseMode | 1048 | Online franchise (connected franchise) |
| **Mut** | **612** | **Madden Ultimate Team** |
| GameManager | 264 | Matchmaking and game sessions |
| Clubs | 133 | |
| GameReporting | 77 | End-of-game reports |
| MiscServiceGateway | 71 | |
| Authentication | 69 | |
| Scouting, FranTkMode, MaddenShare, CareerMode, GridironClub, Stats, Util, Redirector, AssociationLists, Messaging, Mail, … | fewer | |

## Ultimate Team: requests the game can send

There are 154 request types in `Blaze::Mut::`, of which 16 are `Debug_` requests. This list is our build checklist for Ultimate Team. The component and command **numbers** are still unknown; we get them from the capture log.

**Core MUT (lineups, collection, packs, store, auction house, trades, solos and objectives, end of game):**
AcceptTradeOffer, AddCardsToCollection, BidOnAuction, CancelTradeOffer, CommerceHandshake, CompleteNewUserFlowState, CraftCardUpgradeSlotItem, CreateLineup, CreatePack, CreateSalaryLineup, CreateTeam, CreateTrade, DeleteLineup, DeleteMUTUser, DemotePlayerFromDepthChart, DemotePlayerFromEntireDepthChart, DiscardCard, EnableActiveAbility, GenerateDepthChart, GetAuctionBids, GetCardUpgradeTierInfo, GetCollectionInfo, GetCollectionsBonuses, GetCollectionsForCard, GetCollectionsForCategory, GetConfigurationInfo, GetCpuSequencesForCategory, GetCpuTeamGameCategories, GetCpuTeamGamesForSequence, GetDeckPage, GetDepthChartGenerationOptions, GetDepthChart, GetDirectPurchaseItems, GetEligiblePlayerPage, GetFilterData, GetGameData, GetHubData, GetHubOptions, GetInfoPanel, GetIsOverMaxTeams, GetLineupDetail, GetLineupPanelData, GetListStoreItems, GetMissionActionAdvancedLink, GetMissionDataForCampaign, GetMissionDataForMission, GetMissionDataForRoot, GetMyCreatedTrades, GetMyPacks, GetMyTradeOffers, GetNewAwards, GetNewUserFlowPacks, GetNewUserFlowState, GetObjectivePanelData, GetObjectiveTasks, GetPackInfo, GetPackOdds, GetPlayerAbilityData, GetPostedAuctions, GetPremiumChallengeInfo, GetRedeemedCodePopupText, GetRenderData, GetRootCollectionCategories, GetStoreCategoryInfo, GetSubCategoriesForCategory, GetSynergyData, GetTeamInfo, GetTeamPreviewData, GetTotalCurrency, GetTradeOffers, Handshake, MakeDraftPackPicks, MakeTradeOffer, ModifyCardUpgradeSlotItem, ModifyCardUpgradeTier, OpenPack, OptimizeDepthChartBySynergyId, PostAuction, ProcessEndOfGame, ProcessReturningMutUser, ProcessStartOfGame, PurchaseCardOffer, RefreshAuctionDetails, RefundCardsFromCollection, RejectTradeOffer, RemoveCoachFromLineup, RenameLineup, RenameTeam, SearchAuction, SearchTrade, SelectNewUserFlowPack, SetActiveLineup, SetFavoriteTeam, SetNonPlayerItemToActive, SetPlayerToDepthChart, SetTutorialComplete, SynchronizeConsumables, TerminateAuction, TerminateTrade, UpdateMissionFavoriteStatus

**`Mut::Dc` (Draft Champions, plus events such as Solo Battles, Squads, leagues and knockouts):**
CanPlayScenario, CopyExistingTeam, DismissEventScenarios, EvaluateEventQualification, FilterUsersByEvent, GetAvailableScenariosForEvent, GetConfigurationInfo, GetDivisionBreakdown, GetDraftEvents, GetDraftRewardsForEvent, GetEligiblePlayerPage, GetEndEventRewards, GetEventAdvancementProgressInfo, GetEventGroups, GetEventPaymentOptions, GetEventScenarioDetails, GetEventsInGroup, GetGameAndRenderData, GetHubData, GetKnockoutLandingPage, GetLandingPageData, GetLeagueEventDetails, GetLeagueLandingPageData, GetNewUserFlowState, GetSessionUserDepthChart, GetSoloBattlesLandingPageData, GetSquadDepthChart, GetSquadLandingPageData, GetSquadLobbyInfo, GetTournamentBracket, GetUserBarData, GetUserItem, GrantEndEventRewards, Handshake, LockDraftInstance, MakeDraftPick, ProcessEndOfGame, ProcessStartOfGame, ResetEvent, ResetTeam, ResumeDraft, SetPlayerToDepthChart, SetTutorialComplete, StartDraft, UpdateLevel, UpdateSeason

The client's first Ultimate Team calls are probably **Handshake** and then **GetConfigurationInfo**: the game code names `MutManager::HandshakeCommand` and `StartGetConfigurationInfo`. Those are the first two MUT replies to build.

## Card data

The game data uses Frostbite superbundles: `Data/Win32/*.toc` and `.sb`, plus 59 `.cas` archives, with matching `Patch/` overrides. It has `playercontent_sb` (6.8 MB table of contents) and `livecontentupdate/attribsyssb`. Whether card definitions (programs, ratings, abilities) exist locally, or only arrived from the server (`GetRenderData`, `GetPackInfo` and so on), is **[UNKNOWN]**. Finding out needs a Frostbite asset browser such as Frosty or FMT. That is a later phase, done read-only.
