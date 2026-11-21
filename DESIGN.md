# RPC Buddy — Design

Status: **v0.1 implemented** (Phases 0–2 done, Phase 3 in progress: daily use
and testing with friends). Deferred ideas live in [FUTURE_IDEAS.md](FUTURE_IDEAS.md).

## 1. Problem

Discord running as a Flatpak cannot see host processes, so it never shows
which game you are playing. Discord also only shows music for Spotify — not
for Deezer or other players.

RPC Buddy is a desktop app that detects what you are doing and publishes it
as Discord Rich Presence through Discord's local IPC socket.

## 2. Goals and non-goals

**Goals**

- Runs as a Flatpak on KDE Plasma and GNOME (at least).
- Detects Steam games and shows them with their **official** Discord identity
  (name + cover art), as if Discord had detected them itself.
- Shows music from MPRIS players (Deezer, TIDAL, …) as "Listening".
- Comfortable: auto-detection first, guided setup only when needed.
- Modular code base, so the maintainer can add sources later.

**Non-goals (v1)**

- Third-party/user-written modules.
- Games that are not in Discord's detectable list (see FUTURE_IDEAS.md).
- Launchers other than Steam.
- Unofficial Discord clients (Vesktop, Legcord, WebCord, …).
- Translations (English only).

## 3. Acceptance criteria (v1)

| # | Criterion | Status |
|---|---|---|
| 1 | Installed as a locally built Flatpak, the app connects to the official Discord Flatpak **without manual symlinks or Flatseal changes**. | ✅ |
| 2 | On KDE Plasma, a **tray icon** is shown; its menu shows the current activity, per-module toggles, a "pause presence" toggle, and opens the main window. | ✅ |
| 3 | Starting a Steam game that is in Discord's detectable list shows "Playing <Game>" with the game's official cover and elapsed time within a few seconds; quitting the game clears it. | ✅ |
| 4 | Playing music in a supported MPRIS player shows a "Listening" activity with title, artist and (if the player provides a web link) cover art; it is cleared after 30 s of pause. | ✅ |
| 5 | If something cannot be auto-detected (Discord socket, Steam logs), the app explains exactly what to do (copyable `flatpak override` command) instead of failing silently. | ✅ |
| 6 | Works on GNOME as well (without tray icon unless the AppIndicator extension is installed; then window + Background portal). | ⏳ not tested yet |
| 7 | Autostarts into the tray after the first run (user can disable). | ✅ |

## 4. Decisions

| Topic | Decision |
|---|---|
| Language / GUI | Python 3.13 + PySide6 (Qt 6), **Qt Widgets** |
| Discord lib | `pypresence`, wrapped in a thin adapter (see §7) |
| UI language | English only |
| License | GPL-3.0-or-later |
| App ID | `io.github.YetAnotherGerrit.RpcBuddy` |
| Hosting | GitHub (YetAnotherGerrit), public only after a few weeks of local use; Flathub after that. Until then, testers get a single-file bundle (§8.3) |
| Config | One TOML file, edited via GUI, hand-editable; only values that differ from the defaults are saved, so changed defaults reach existing installs |
| Discord clients | Official only. Flatpak Discord works out of the box; Canary (Flatpak) and Snap are permitted but untested; Discord installed without Flatpak needs a `flatpak override` (setup check offers it) |
| Game identity | Official Discord application ID per game (detectable list) |
| Music identity | Neutral Discord app "RPC Buddy", application ID `1573024567658549388` (with app icon); users can replace it with their own app's ID. The activity `name` is set to the source's name (e.g. "Deezer") |
| Music status line | `status_display_type` configurable (artist / app name / title); default **artist** until it is known how Spotify shows for most users |
| Steam detection | Steam's console log. A Steam Web API fallback was planned but is not implemented (no need so far) |
| Spotify | Opt-in setting "Include Spotify" (default off): Discord shows Spotify itself when the account is linked. The setup check asks once: linked / show via RPC Buddy / don't use Spotify. Auto-detecting the link would need OAuth with a client secret → rejected |
| Game vs. music | Both published in parallel; Discord shows both, the game wins the status line — no own priority logic |
| Unknown games | Not shown in v1 |
| Autostart | On by default (applied when the first-run setup check is closed with Done), starts with `--background` into the tray; Flatpak: XDG Background portal |
| Hide list | Games per Steam app, music per source (player/service); hidden with "Hide" on the activity card in the main window, shown again via the card or the chips under Hidden |
| Setup check | First-run dialog, reopenable from the main window |
| Main window size | Fixed default 600×860 for Full HD screens, capped at 90% of smaller screens |
| Main window look | "Now on Discord" layout: activity cards like Discord's own, toggle switches, sources list, hidden chips (chosen from three mockups, 2026-11) |
| Light / dark | No hard-coded theme: colours are derived from the system palette (incl. the accent colour) and rebuilt when the desktop switches |
| Closing the window | Keeps running in the tray (explained in the footer); the first time, a desktop notification says how to quit. Without a tray, closing quits |

## 5. Architecture

```
┌──────────────────────────── rpc-buddy process ──────────────────────────────┐
│                                                                             │
│  GUI thread (Qt)                           Core thread (asyncio)            │
│  ┌───────────────┐  EngineState via        ┌──────────────────────────────┐ │
│  │ Tray icon     │◄─ Qt signal (queued) ───│ Engine                       │ │
│  │ Main window   │                         │  ├─ supervises modules       │ │
│  │ Setup check   │── engine.set_*() ──────►│  │   (SteamModule,           │ │
│  └───────────────┘  (call_soon_threadsafe) │  │    MprisModule, …)        │ │
│                                            │  ├─ rules: pause, hide list, │ │
│                                            │  │   newest per client_id    │ │
│                                            │  └─ Config (TOML)            │ │
│                                            │         │ desired activities │ │
│                                            │         ▼                    │ │
│                                            │ DiscordSink                  │ │
│                                            │  one IPC connection per      │ │
│                                            │  client_id, reconnects,      │ │
│                                            │  rate limiting               │ │
│                                            │                              │ │
│                                            │ DetectableCache (game list)  │ │
│                                            └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **Core and GUI are decoupled.** The `Engine` (`engine.py`) runs its own
  asyncio loop in a worker thread. The GUI calls its thread-safe `set_*`
  methods; the engine reports an immutable `EngineState` snapshot, delivered
  to the GUI thread through a queued Qt signal (`EngineBridge`). The core can
  also run headless (`rpc-buddy --headless`).
- **Modules** (`module.py`, `modules/`) are internal packages, registered in
  `modules/__init__.py`. Each module:
  - implements `async run()` — runs until cancelled; a crash is logged and the
    module restarted after 30 s,
  - declares `settings` (`Setting`: text / choice / int / bool); the main
    window builds its form from them, a change restarts the module,
  - calls `ctx.publish(activity, summary, hide_key, hide_label)` —
    `hide_key` (e.g. `steam:<appid>`, `mpris:<source>`) makes it hideable,
  - reports `ctx.set_health(Health)` (OK / starting / needs setup / error +
    hint) for the main window and the setup check.
- **Activity** (`activity.py`, independent of pypresence): `client_id`,
  `type` (playing / listening / watching), `name`, `details`, `state`,
  `large_image`/`large_text`, `small_image`/`small_text`, `start`/`end`,
  `status_display`.
- **Engine rules:** pause and hide list remove activities; if several sources
  use the same `client_id`, the newest wins. No priority between game and
  music: Discord shows activities of different apps side by side (E1).
- **DiscordSink** (`discord.py`) keeps one IPC connection per `client_id`
  (a game's ID or the RPC Buddy ID), opens/closes connections as activities
  come and go, detects lost connections and reconnects after Discord
  restarts, and keeps ≥ 4 s between updates per connection (Discord allows
  about 5 per 20 s).

## 6. Modules

### 6.1 Steam

- Tails `logs/console_log.txt` in the Steam root (verified in E3 — start and
  stop detected within ~1 s):
  ```
  [2026-01-01 12:00:00] Game process added : AppID 1000001 "…"
  [2026-01-01 12:00:05] Game process updated : AppID 1000001 "…"
  [2026-01-01 13:15:00] Game process removed: AppID 1000001 "…"
  ```
  On start, the whole current log is replayed to find a game that is already
  running. A new log (Steam restart, detected by inode/size) resets the
  state. With several games running, the most recently started one is shown.
- Steam roots probed: `~/.local/share/Steam`, `~/.steam/steam`,
  `~/.var/app/com.valvesoftware.Steam/.local/share/Steam` and
  `…/com.valvesoftware.Steam/data/Steam` (the Flatpak Steam paths are not
  verified yet).
- Not used: `registry.vdf` `RunningAppID` — current Steam does not write it,
  not even while a game runs (E3). Not implemented: `content_log.txt`
  ("App Running") as a cross-check, Steam Web API fallback.

Identity mapping: the shared, store-agnostic **DetectableCache** service
(`detectable.py`) downloads
`https://discord.com/api/v10/applications/detectable` (~13 MB, ~25k apps) at
most once a day and stores a compact index
`distributor → sku id → (discord_app_id, name, icon_hash, cover_image_hash)`.
Distributors in the list (2026-11): steam ~20k, xbox ~8k, epic ~2.6k,
google_play ~1.7k, gog 64, uplay, battlenet, microsoft. The Steam module looks
up `("steam", appid)`; future modules (e.g. Heroic → epic/gog) use their own
distributor. On a miss, the index is refreshed early if it is older than 6 h.
Images: `https://cdn.discordapp.com/app-icons/{id}/{hash}.png`.

Activity: `client_id` = game's Discord ID, type Playing, start = game start,
large image = cover (or icon).

### 6.2 MPRIS (music)

- Polls the session bus every 2 s (`ListNames`, `GetAll` on the player
  interface — no introspection).
- Which players count (`players.py`):
  - dedicated music players (Elisa, Rhythmbox, Strawberry, Deezer, TIDAL Hi-Fi,
    …), plus apps recognised by their MPRIS `Identity` (e.g. Electron apps),
  - browsers only when the track's `xesam:url` points to a music site
    (Deezer, TIDAL, YouTube Music, SoundCloud, Apple Music, Bandcamp) — plain
    browser videos are ignored (E4),
  - video players (VLC, mpv) are ignored,
  - Spotify (app, `spotifyd`, `ncspot`, web player) only with "Include
    Spotify".
- Which track wins (`selector.py`): a playing player beats paused ones; the
  shown one keeps priority, otherwise the most recently started. After
  pausing, the track stays without timestamps for `pause_timeout` (30 s),
  then disappears. Start timestamps are kept stable against polling jitter
  (only jumps > 3 s count as a seek).
- Activity: `client_id` = configured music app ID (default: RPC Buddy),
  type Listening, `name` = source (profile card: "Listening to Deezer", E2),
  `details` = title, `state` = artist, `large_text` = album, start/end from
  position/length, `status_display` as configured. Discord needs 2–128
  characters per text field; shorter/longer values are padded/cut.
- Cover art: `mpris:artUrl` only if it is https (Discord proxies external
  images). Browsers usually only provide a local `file://` cover. **No online
  cover lookups** — they would send what the user listens to to a third party
  (decided 2026-11, see FUTURE_IDEAS.md). Without a cover, Discord should show
  the RPC Buddy app icon instead (not verified yet).

## 7. Discord connection

- `pypresence`'s `AioPresence` is wrapped in `PypresenceConnection`, which
  isolates its quirks — notably `AioPresence.close()` closes the whole asyncio
  event loop, so the adapter disconnects manually.
- Socket discovery is pypresence's: `discord-ipc-*` in `$XDG_RUNTIME_DIR`,
  `app/com.discordapp.Discord`, `app/com.discordapp.DiscordCanary` and
  `snap.discord`.
- The Flatpak manifest grants the Discord, Discord Canary and Snap directories
  up front, so the standard setup needs no user action. A Discord installed
  without Flatpak puts its socket directly into `$XDG_RUNTIME_DIR`; that needs
  `flatpak override --user --filesystem=xdg-run/discord-ipc-0 <app-id>`, and
  Discord has to start before RPC Buddy (the socket must exist when the
  sandbox is set up).
- Over IPC without OAuth, Discord only reveals the logged-in user's profile
  (READY), not their activities or account connections (checked 2026-11).

## 8. Flatpak

### 8.1 Build

- Runtime `org.kde.Platform//6.11`, SDK `org.kde.Sdk//6.11`, base
  `io.qt.PySide.BaseApp//6.11`. Python wheels (pypresence, tomli-w,
  dbus-fast for x86_64/aarch64) are listed in the manifest.
- Size: the BaseApp ships build tools and extras (LLVM/Clang, numpy, PyOpenGL,
  all Qt bindings, FFmpeg for QtMultimedia). `flatpak/cleanup-pyside.sh` removes
  them, keeping only QtCore, QtGui, QtWidgets and QtNetwork: installed size
  ~361 MB → ~22 MB. Using another Qt module means adding it to `KEEP` there.

### 8.2 Permissions

All narrow, no host escape:

- `--socket=wayland`, `--socket=fallback-x11`, `--share=ipc`, `--device=dri`
- `--share=network` (Discord's game list)
- `--filesystem=xdg-run/app/com.discordapp.Discord:ro`, `…DiscordCanary:ro`,
  `xdg-run/snap.discord:ro`
- `--filesystem=~/.local/share/Steam/logs:ro`,
  `--filesystem=~/.var/app/com.valvesoftware.Steam/.local/share/Steam/logs:ro`
- `--talk-name=org.mpris.MediaPlayer2.*`
- `--talk-name=org.kde.StatusNotifierWatcher` and
  `--own-name=org.kde.StatusNotifierItem-2-2` (tray; inside the sandbox the
  app's PID is always 2, Qt registers this name)
- `--talk-name=org.freedesktop.Notifications` (the one-time "still running in
  the tray" notification)

Verified from inside the `org.kde.Platform//6.11` runtime (E5). The session
bus must not be disabled (`flatpak run --sandbox` breaks MPRIS and the tray).
Autostart uses the XDG Background portal, which needs no extra permission.

Files: config `$XDG_CONFIG_HOME/rpc-buddy/config.toml`, cache (game list
index) `$XDG_CACHE_HOME/rpc-buddy/` — inside the Flatpak under
`~/.var/app/io.github.YetAnotherGerrit.RpcBuddy/`.

### 8.3 Test builds for friends

Until there is a public repository, testers get a single-file bundle
(~5 MB; the KDE runtime is pulled from Flathub on install):

```bash
flatpak-builder --repo=repo --force-clean build-dir flatpak/io.github.YetAnotherGerrit.RpcBuddy.yml
flatpak build-bundle repo rpc-buddy.flatpak io.github.YetAnotherGerrit.RpcBuddy \
    --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo
```

Testers install with `flatpak install --user rpc-buddy.flatpak`; a newer
bundle replaces the old one. No automatic updates. x86_64 only so far.

## 9. GUI

- **Tray** (primary on KDE): current activity, Discord status, pause toggle,
  module toggles, "Open RPC Buddy…", "Quit"; left click opens the main window.
- **Main window** (`gui/window.py`), top to bottom:
  - header with the app icon and a Discord status pill (green / amber),
  - **Now on Discord**: one card per activity — cover (game covers from
    Discord's CDN via `gui/covers.py`, otherwise a coloured placeholder),
    "PLAYING · STEAM" / "LISTENING · DEEZER", title, elapsed time or song
    progress (updated every second), **Hide** / **Show**; an empty or
    "paused" card (with Resume) when nothing is shown,
  - toggle switches: pause presence, start with the desktop,
  - **Sources**: per module icon, health, ⚙ (settings dialog generated from
    the module's `settings`) and an on/off switch,
  - **Hidden**: chips, click to show again,
  - fixed footer: what closing does, "Run setup check…", "Hide to tray",
    "Quit RPC Buddy".
  Closing hides it to the tray (quits if no tray); the first time, a desktop
  notification explains how to quit.
- **Look** (`gui/style.py`, `gui/widgets.py`): colours computed from the system
  palette (window, text, accent) into a small stylesheet, re-applied when the
  palette changes (light/dark switch). Widgets: toggle switch, wrapping row,
  rounded cover image.
- **Setup check** (first run, reopenable): Discord, Steam games, music, tray
  icon, autostart, plus the Spotify question — coloured status and copyable
  `flatpak override --user …` commands where something is missing; rows
  scroll on small screens. The app cannot change its own sandbox permissions.
  Logic in `setup_checks.py` (Qt-free, tested).
- **Single instance**: a second launch asks the running one to show its
  window (local socket in `$XDG_RUNTIME_DIR/app/<app-id>/`).
- `--background` starts into the tray without opening the window.

## 10. Development workflow

- Daily work: Python venv on the host, managed with `uv`, with Python pinned
  to the version of the Flatpak runtime (3.13; host Python 3.15 may lack
  PySide6 wheels).
  > **Warning:** this works because every dependency is a pip wheel. As soon
  > as we need **system packages** (e.g. a C library without wheels, distro
  > tools), switch to a **Distrobox** container instead of installing
  > things on the immutable host.
- Packaging/real-world test: `flatpak-builder --user --install` on the host
  (some distributions ship it; also available as the `org.flatpak.Builder` Flatpak).
- Tests: `pytest` (parsers, selector, engine rules, sink, cache, config,
  setup checks — no Discord needed); lint/format with `ruff`.
- Repo hygiene: no real game/song titles, their IDs or real play times in
  committed files — tests and docs use made-up values.

## 11. Plan

**Phase 0 — experiments (done 2026-11-19, pypresence 4.6.2)**

- **E1 ✅** Two IPC connections from one process (a game's Discord ID + RPC
  Buddy ID) work in parallel: the profile shows both cards; the game wins the
  member-list status line.
- **E2 ✅** Listening (`type: 2`) works. `status_display_type = STATE` makes
  the member list show "♫ <artist>". The profile card heading shows the
  app name ("Listening to RPC Buddy") unless the activity `name` is set —
  `name: "Deezer"` gives "Listening to Deezer".
- **E3 ✅** Steam logs report start/stop within ~1 s; `registry.vdf` has no
  `RunningAppID` → dropped.
- **E4 ✅** Deezer web in a browser exposes MPRIS with title, artist, album,
  length, `xesam:url` (deezer.com) and a local `file://` cover.
- **E5 ✅** From inside the KDE runtime with the planned permissions: Discord
  via the `:ro` socket mount, Steam logs, MPRIS and the tray icon all work.

Also verified: Discord's detectable list maps Steam games to their official
Discord app (Steam app id → Discord application id, with cover art).

**Phase 1 ✅** — core, DiscordSink, Steam module, DetectableCache, tray with
status and toggles, first Flatpak build.

**Phase 2 ✅** — MPRIS module, pause and hide list, main window, setup check,
autostart.

**Phase 3 (in progress)** — polish, weeks of daily use, then GitHub public,
then Flathub.

- ✅ Flatpak size 361 MB → 22 MB
- ✅ README for users and contributors
- ✅ App icon for the RPC Buddy Discord app
- ✅ Spotify opt-in with setup question
- ✅ Single-file bundle for testers
- ✅ Redesigned main window ("Now on Discord"), clearer close/quit
- ⏳ Daily use and feedback from testers
- ⏳ Before going public: review the whole history, repository description

## 12. Open questions

- How does Spotify appear in the member list for most users? (Decides the
  default of the music status line, §4.)
- Untested: GNOME, Flatpak Steam, Discord Canary / Snap, aarch64.
