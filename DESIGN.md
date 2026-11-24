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
| Discord clients | Official only. Flatpak Discord works out of the box, in any start order (folder mounted with `:create`, E8); Canary (Flatpak) and Snap are permitted but untested; Discord installed without Flatpak needs a `flatpak override`, must start before RPC Buddy, and RPC Buddy must be restarted after Discord restarts (setup check explains; a self-restart via the Flatpak portal's `Spawn` is a possible later step) |
| Game identity | Official Discord application ID per game (detectable list) |
| Music identity | Neutral Discord app "RPC Buddy", application ID `1573024567658549388` (with app icon); users can replace it with their own app's ID. The activity `name` is set to the source's name (e.g. "Deezer") |
| Music status line | `status_display_type` configurable (artist / app name / title); default **artist** until it is known how Spotify shows for most users |
| Steam detection | Steam's console log. A Steam Web API fallback was planned but is not implemented (no need so far) |
| Spotify | Opt-in setting "Include Spotify" (default off): Discord shows Spotify itself when the account is linked. The setup check asks once: linked / show via RPC Buddy / don't use Spotify. Auto-detecting the link would need OAuth with a client secret → rejected |
| Game vs. music | Both published in parallel; Discord shows both, the game wins the status line — no own priority logic |
| Unknown games | Not shown in v1 |
| Steam Invisible / Offline | Game not sent to Discord (setting "Hide games while I'm invisible on Steam", default on); still shown greyed out in the main window with the reason. Needs read access to Steam's `userdata` (accepted 2026-11) |
| Autostart | On by default (applied when the first-run setup check is closed with Done), starts with `--background` into the tray; Flatpak: XDG Background portal |
| Hide list | Games per Steam app, music per source (player/service); hidden with "Hide" on the activity card in the main window, shown again via the card or the chips under Hidden |
| Setup check | First-run dialog, reopenable from the main window |
| Steam in an unusual place | Choose its folder in the desktop's file dialog (FileChooser portal → document portal, access persists; E7); `flatpak override` as fallback; "I don't use Steam" switches the module off |
| Main window size | Fixed default 600×860 for Full HD screens, capped at 90% of smaller screens |
| Main window look | "Now on Discord" layout (mockup A; the section is titled "Your activity"): activity cards like Discord's own, toggle switches, sources list, hidden chips (chosen from three mockups, 2026-11) |
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
  - calls `ctx.publish(activity, summary, hide_key, hide_label, withheld)` —
    `hide_key` (e.g. `steam:<appid>`, `mpris:<source>`) makes it hideable;
    `withheld` (a short reason) keeps it off Discord but shows it greyed out
    in the main window,
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
  If Steam crashes or the PC is switched off while a game runs, the log never
  gets a "removed" line; so a game that "runs" for more than 12 hours
  (hardcoded `MAX_RUNNING`) is treated as stopped. Simple first fix — real
  sessions over 12 hours lose their status too.
- Steam roots probed: the folder from the setting "Steam folder" (if set —
  typed, or chosen via the desktop's file dialog, then a
  `/run/user/<uid>/doc/<id>/…` path), then `~/.local/share/Steam`, `~/.steam/steam`,
  `~/.var/app/com.valvesoftware.Steam/.local/share/Steam` and
  `…/com.valvesoftware.Steam/data/Steam` (the Flatpak Steam paths are not
  verified yet).
- **Steam status** (`persona.py`): Steam's UI stores the status the user
  picked in `userdata/<account>/config/localconfig.vdf` →
  `UserLocalConfigStore › WebStorage › FriendStoreLocalPrefs_<account>` →
  `"ePersonaState": n` and rewrites the file within seconds (verified
  2026-11; not in any log). The most recently written account file is used;
  it is re-read only when its timestamp changes. Invisible (7) or Offline (0)
  → the game is published as *withheld* ("you're invisible on Steam").
  Missing file or entry → treated as online.
- Not used: `registry.vdf` `RunningAppID` — current Steam does not write it,
  not even while a game runs (E3). Not implemented: `content_log.txt`
  ("App Running") as a cross-check, Steam Web API fallback.

Identity mapping: the shared, store-agnostic **DetectableCache** service
(`detectable.py`) downloads
`https://discord.com/api/v10/applications/detectable` (~13 MB, ~25k apps) at
most once a day **in a short-lived child process**
(`python -m rpc_buddy.detectable --refresh <db>`) that writes an SQLite
database (~5 MB) `games(distributor, sku → discord_app_id, name, icon_hash,
cover_image_hash)`; the app only queries single rows. Parsing the JSON in the
app itself would leave it ~60 MB bigger for good (Python keeps freed memory;
`malloc_trim` doesn't help) — see §14.
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
  up front, so the standard setup needs no user action.
- **Start order (E8, 2026-11):** a folder that doesn't exist when the sandbox
  starts is never visible in it, even if it appears later. The folder
  `$XDG_RUNTIME_DIR/app/com.discordapp.Discord` only exists once the Discord
  Flatpak has run since login — so RPC Buddy autostarting before Discord stayed
  "not reachable" until restarted. Fix: `:create` for that folder (Flatpak
  creates it when RPC Buddy starts; Discord later puts its socket there). Cost:
  `:create` implies read-write access to Discord's runtime folder; RPC Buddy
  only connects to the socket. Canary and Snap stay `:ro`.
- A Discord installed without Flatpak puts its socket directly into
  `$XDG_RUNTIME_DIR`; that needs
  `flatpak override --user --filesystem=xdg-run/discord-ipc-0 <app-id>`
  (visible in `/.flatpak-info`, so the setup check adapts its text). Such a
  single-file mount only works if Discord started first, and goes stale when
  Discord restarts (new socket) — RPC Buddy must then be restarted.
- While Discord is not reachable, the tray icon gets an amber "!" badge.
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
- `--filesystem=xdg-run/app/com.discordapp.Discord:create` (any start order,
  see §7), `…DiscordCanary:ro`, `xdg-run/snap.discord:ro`
- `--filesystem=~/.local/share/Steam/logs:ro`,
  `--filesystem=~/.var/app/com.valvesoftware.Steam/.local/share/Steam/logs:ro`
- `--filesystem=~/.local/share/Steam/userdata:ro` (+ the Flatpak Steam path):
  Steam's online status. Flatpak permissions can't use wildcards, so this is
  the whole `userdata` folder (read-only) although only one file is read
- `--talk-name=org.mpris.MediaPlayer2.*`
- `--talk-name=org.kde.StatusNotifierWatcher` and
  `--own-name=org.kde.StatusNotifierItem-2-2` (tray; inside the sandbox the
  app's PID is always 2, Qt registers this name)
- `--talk-name=org.freedesktop.Notifications` (the one-time "still running in
  the tray" notification)

Verified from inside the `org.kde.Platform//6.11` runtime (E5). The session
bus must not be disabled (`flatpak run --sandbox` breaks MPRIS and the tray).
Autostart uses the XDG Background portal, which needs no extra permission.
Folders chosen in the file dialog (FileChooser portal) are shared through the
document portal — also no extra permission; the access is stored in Flatpak's
permission store (the portal grants read and write).

Files: config `$XDG_CONFIG_HOME/rpc-buddy/config.toml`, cache (game list
database `detectable.sqlite3`) `$XDG_CACHE_HOME/rpc-buddy/` — inside the Flatpak under
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
  - **Your activity**: one card per activity — cover (game covers from
    Discord's CDN via `gui/covers.py`, otherwise a coloured placeholder),
    "PLAYING · STEAM" / "LISTENING · DEEZER", title, elapsed time or song
    progress (updated every second), **Hide** / **Show**. Activities not sent
    to Discord stay visible, dimmed, with an overlay "Not on Discord —
    <reason>". Reasons, first wins: hidden by you, presence paused (pause is
    a preview: games can be hidden before they ever reach Discord), a module's
    reason (e.g. invisible on Steam). An empty or "paused" card (with Resume)
    when there is no activity at all,
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
  scroll on small screens. Rows can offer action buttons (e.g. Steam: "Choose
  Steam folder…", "I don't use Steam"); the command stays as a fallback.
  Logic in `setup_checks.py` (Qt-free, tested).
- **Folder settings** (`Setting(kind="folder")`): text field plus "Choose…",
  which opens the desktop's file dialog through the FileChooser portal
  (`portal.py`, shared with autostart). Qt's own dialog is useless inside the
  sandbox (it only sees the sandbox, E7).
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
- CI: `.github/workflows/ci.yml` runs ruff and pytest on Ubuntu 24.04 for
  every push and pull request (Qt needs a few system libraries even without a
  display; `QT_QPA_PLATFORM=offscreen`).
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
- **E8 ✅** (2026-11, Discord started after RPC Buddy) A runtime folder
  created after the sandbox started is invisible inside it (`:ro`); with
  `:create`, Flatpak creates it at sandbox start and a socket placed there
  later is visible.
- **E7 ✅** (2026-11, folder for Steam in an unusual place) Qt's
  `QFileDialog` inside the sandbox shows only the (empty) sandbox → unusable.
  The FileChooser portal (`OpenFile`, `directory: true`) shows the desktop's
  dialog; the folder arrives as `/run/user/<uid>/doc/<id>/<name>`, is
  readable, log appends are seen immediately, and access survives a restart.
  E7d: the Steam module with such a folder as "Steam folder" detects a game
  start inside the sandbox.

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
- ✅ Respect Steam's Invisible / Offline status
- ✅ Pause shows a preview of the activities (hide before publishing)
- ✅ Security review (§13) and performance tuning (§14)
- ⏳ Daily use and feedback from testers
- ✅ Prepared for GitHub (2026-11-22): history reviewed (no personal data,
  secrets or real titles in any commit), CI workflow, README screenshots
  (`tools/make_screenshots.py`, made-up content), CONTRIBUTING.md,
  SECURITY.md, installation via GitHub Releases
- ⏳ Push to GitHub, make it public, release `v0.1.0` with the bundle
- ⏳ Before publishing on Flathub — store listing (`flatpak/*.metainfo.xml`):
  - **Description tone (wanted):** start from the user's problem, casual and
    honest, e.g. *"You run Discord as a Flatpak and it doesn't show the game
    you're playing? There are lots of ways to fix that — RPC Buddy aims to be
    one of the easiest: install it, start it once, done."* Then what it shows
    (Steam games with official name and artwork, music, side by side) and
    what makes it comfortable (setup check, tray, hide list, Steam's
    Invisible status).
  - Shorter summary (~35 characters), e.g. "Show your games and music on
    Discord".
  - ✅ Screenshots with captions (light and dark, made-up content) — in the
    metainfo, pointing to the `v0.1.0` tag in the public repo.
  - ✅ `developer id` in lowercase; links for bug tracker, source code and
    contributing.
  - `<branding>` colours; check the OARS age rating (sharing activity with
    Discord → `social-info`?); release notes per version.
  - Run `appstreamcli validate --pedantic` and Flathub's
    `flatpak-builder-lint` (via `org.flatpak.Builder`).

## 12. Open questions

- How does Spotify appear in the member list for most users? (Decides the
  default of the music status line, §4.)
- Untested: GNOME, Flatpak Steam, Discord Canary / Snap, aarch64.

## 13. Security assessment (2026-11)

**Threat model.** RPC Buddy runs in a narrow Flatpak sandbox, opens no
network ports and executes nothing it downloads. The only data an outsider
controls are music titles/artists/albums (and cover URLs) of tracks played on
**websites** — the browser passes the site's metadata on via MPRIS.

Scans: Bandit (only false positives: fixed-URL `urlopen`, an `assert`, an
intentional `try/except: pass`), pip-audit on the locked dependencies (no
known vulnerabilities). Python wheels are pinned with SHA-256 in the manifest
and in `uv.lock`.

| # | Finding | Status |
|---|---|---|
| 1 | Titles shown in Qt labels could be rendered as HTML (UI spoofing, local images) | Fixed: labels are plain text unless they show our own escaped status HTML |
| 2 | Covers loaded from any https URL without limits | Fixed: PNG/JPEG/WebP only (checked by signature), ≤ 5 MB, 15 s timeout |
| 3 | Game names / app ids logged at info level (may persist in the journal) | Fixed: only with `--debug` |
| 4 | Tray tooltip contained titles (rendered by the desktop, possibly as HTML) | Fixed: general status only; `&` escaped in menu entries |
| 5 | Autostart entry outside the Flatpak: unescaped path in `Exec=` | Accepted (development only) |
| 6 | Whatever a website sets as title appears in the Discord status | Inherent; hide list and pause |

Rules for new code: show external text as plain text; never load or execute
anything from activity data beyond the checks above; keep names, titles and
ids out of info-level logs.

## 14. Performance (2026-11)

Goal: negligible background impact on a gaming PC. Measured in the Flatpak,
idle in the tray (KDE Plasma):

| | Value |
|---|---|
| CPU | ~0 (0.08 % of one core before the changes below, 0 ticks in 30 s after) |
| Memory (RSS) | ~109 MB, of which ~70 MB are shared libraries (Qt, Python) |
| Wakeups | GUI thread 0/s in the tray; core thread ~2/s (Steam log + status every 1 s, MPRIS every 2 s) |
| For comparison | Discord ~1.5 GB, Steam ~0.5 GB + steamwebhelper ~1.8 GB |

Decisions:

- **Game list in a child process + SQLite** (see §6.1): saves ~75 MB after the
  first game / daily refresh.
- **Main window and setup dialog built on first open**: ~17 MB less when
  started into the tray (autostart).
- **No GUI timers while hidden**: the card timer runs only while the window
  is visible; Ctrl+C/SIGTERM use `signal.set_wakeup_fd` + `QSocketNotifier`
  instead of a polling timer.
- Not done (little gain for more code or risk): `inotify` instead of polling
  the Steam log, MPRIS signals instead of polling, a smaller toolkit than Qt.
