# rpc-buddy — Design

Status: **draft**, nothing implemented yet. Deferred ideas live in
[FUTURE_IDEAS.md](FUTURE_IDEAS.md).

## 1. Problem

Discord running as a Flatpak cannot see host processes, so it never shows
which game you are playing. Discord also only shows music for Spotify — not
for Deezer or other players.

rpc-buddy is a desktop app that detects what you are doing and publishes it
as Discord Rich Presence through Discord's local IPC socket.

## 2. Goals and non-goals

**Goals**

- Runs as a Flatpak on KDE Plasma and GNOME (at least).
- Detects Steam games and shows them with their **official** Discord identity
  (name + cover art), as if Discord had detected them itself.
- Shows music from MPRIS players (Deezer client, Tidal, …) as "Listening".
- Comfortable: auto-detection first, guided setup only when needed.
- Modular code base, so the maintainer can add sources later.

**Non-goals (v1)**

- Third-party/user-written modules.
- Games that are not in Discord's detectable list (see FUTURE_IDEAS.md).
- Launchers other than Steam.
- Unofficial Discord clients (Vesktop, Legcord, WebCord, …).
- Translations (English only).

## 3. Acceptance criteria (v1)

1. Installed as a locally built Flatpak, the app connects to the official
   Discord Flatpak **without manual symlinks or Flatseal changes**.
2. On KDE Plasma, a **tray icon** is shown; its menu shows the current
   activity, per-module toggles, a "pause presence" toggle, and opens the
   main window.
3. Starting a Steam game that is in Discord's detectable list shows
   "Playing <Game>" with the game's official icon/cover and elapsed time,
   within a few seconds; quitting the game clears it.
4. Playing music in an allowlisted MPRIS player shows a "Listening" activity
   with title, artist and (if possible) cover art; it is cleared after 30 s
   of pause.
5. If something cannot be auto-detected (Discord socket, Steam logs), the app
   explains exactly what to do (copyable `flatpak override` command or
   Flatseal steps) instead of failing silently.
6. Works on GNOME as well (without tray icon unless the AppIndicator extension
   is installed; then window + background portal).
7. Autostarts minimized to tray after the first run (user can disable).

## 4. Decisions

| Topic | Decision |
|---|---|
| Language / GUI | Python + PySide6 (Qt 6), **Qt Widgets** |
| Discord lib | `pypresence` |
| UI language | English only |
| License | GPL-3.0-or-later |
| App ID | `io.github.YetAnotherGerrit.RpcBuddy` |
| Hosting | GitHub (YetAnotherGerrit), public only after a few weeks of local use; Flathub after that |
| Config | One TOML file, edited via GUI, hand-editable |
| Discord clients | Official only: Stable, PTB, Canary — Flatpak, native, Snap |
| Game identity | Official Discord application ID per game (detectable list) |
| Music identity | Neutral Discord app "rpc-buddy", application ID `1573024567658549388`; users can replace it with their own registered app's ID. The activity `name` is overridden with the player's name (e.g. "Deezer") |
| Music status line | `status_display_type` configurable (app name / artist / title); default **artist** until it is known how Spotify shows for most users |
| Steam detection | Logs → Steam Web API (opt-in) |
| Game vs. music | Both published in parallel; Discord shows both, game wins the status line — no own priority logic |
| Unknown games | Not shown in v1 |
| Autostart | On by default (applied when the first-run setup check is closed with Done), starts with `--background` into the tray; Flatpak: XDG Background portal |
| Hide list | Games per Steam app, music per source (player/service); hiding only in the main window; recently seen items (session only, max 20) are offered |
| Setup check | First-run dialog, reopenable from the main window |
| Native (non-Flatpak) Discord | Not requested by default; the setup check offers a copyable `flatpak override` and the note to start Discord first |
| Main window size | Fixed default 600×860 for Full HD screens, capped at 90% of smaller screens |

## 5. Architecture

```
┌─────────────────────────── rpc-buddy process ─────────────────────────────┐
│                                                                           │
│  GUI thread (Qt)                         Core thread (asyncio)            │
│  ┌──────────────┐   Qt signals /         ┌─────────────────────────────┐  │
│  │ Tray icon    │◄──thread-safe queue───►│ ModuleManager               │  │
│  │ Main window  │                        │  ├─ SteamModule             │  │
│  │ Setup wizard │                        │  ├─ MprisModule             │  │
│  └──────────────┘                        │  └─ …                       │  │
│                                          │        │ ActivityUpdate      │  │
│                                          │        ▼                     │  │
│                                          │ PresenceRouter              │  │
│                                          │  (pause, hide list, rules)  │  │
│                                          │        │                    │  │
│                                          │        ▼                    │  │
│                                          │ DiscordSink                 │  │
│                                          │  one IPC connection per     │  │
│                                          │  client_id, reconnects,     │  │
│                                          │  rate limiting              │  │
│                                          │                             │  │
│                                          │ Services: DetectableCache,  │  │
│                                          │  SteamStore, ConfigStore    │  │
│                                          └─────────────────────────────┘  │
└───────────────────────────────────────────────────────────────────────────┘
```

- **Core and GUI are decoupled.** The core runs its own asyncio loop in a
  worker thread and talks to the GUI only via messages. The core can also run
  headless (`rpc-buddy --headless`) for testing and debugging.
- **Modules** are internal Python packages under `rpc_buddy/modules/`,
  registered in a central list. Each module:
  - declares its settings (used to generate its settings page),
  - has `start()` / `stop()`,
  - publishes `ActivityUpdate(source=module_id, activity=Activity | None)`,
  - reports a health status (OK / needs setup / error + hint) for the wizard.
- **Activity** (internal model, independent of pypresence):
  `client_id` (None → rpc-buddy app), `type` (playing/listening/watching),
  `details`, `state`, `large_image`/`large_text`, `small_image`/`small_text`,
  `start`/`end` timestamps, `status_display_type`.
- **PresenceRouter** applies global rules: pause toggle, per-game hide list.
  No priority logic: activities with different `client_id`s are shown in
  parallel by Discord, and a game wins the status line (E1).
- **DiscordSink** keeps one IPC connection per `client_id` (a game's ID or
  the rpc-buddy ID), opens/closes connections as activities come and go,
  reconnects when Discord restarts, and respects Discord's rate limit
  (~5 updates / 20 s).

## 6. Modules

### 6.1 Steam

Detection, in order:

1. **Logs** (primary, verified in E3 — start and stop detected within ~1 s):
   tail `logs/console_log.txt` in the Steam root:
   ```
   [2026-01-01 12:00:00] Game process added : AppID 1000001 "…"
   [2026-01-01 12:00:05] Game process updated : AppID 1000001 "…"
   [2026-01-01 13:15:00] Game process removed: AppID 1000001 "…"
   ```
   Cross-check / fallback signal: `logs/content_log.txt`
   `AppID <id> state changed : Fully Installed,App Running,` (and the same
   line without `App Running` on exit). Handle log rotation.
2. **Steam Web API** (opt-in, wizard): `GetPlayerSummaries` with API key +
   SteamID64, polled; requires the game details to be public.

Not used: `registry.vdf` `RunningAppID` — current Steam does not write it,
not even while a game runs (E3).

Steam roots to probe:

- Native: `~/.local/share/Steam` (also `~/.steam/steam` symlink)
- Flatpak: `~/.var/app/com.valvesoftware.Steam/.local/share/Steam` (verify)

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

Activity: `client_id` = game's Discord ID, type Playing, start timestamp =
game start, large image = cover (or icon).

### 6.2 MPRIS (music)

- Watches `org.mpris.MediaPlayer2.*` on the session bus.
- Allowlist of players. Browsers are only accepted when the track's
  `xesam:url` points to a known music site — e.g. Deezer web in a browser
  reports `xesam:url = https://www.deezer.com/…` (E4). Plain browser videos
  are ignored.
- Activity: `client_id` = configured music app ID (default: rpc-buddy,
  `1573024567658549388`; a user may enter the ID of their own app from the
  Discord Developer Portal to get their own name/assets), type Listening,
  `name` = player/service name (e.g. "Deezer" — the profile card then reads
  "Listening to Deezer", E2), `details` = title, `state` = artist,
  `large_text` = album, start/end from position/length,
  `status_display_type` as configured.
- Cleared after 30 s paused (configurable).
- Cover art: use `mpris:artUrl` only if it is https (Discord proxies external
  images). Browsers often only provide a local `file://` cover → online lookup is
  deferred, see FUTURE_IDEAS.md.

## 7. Discord connection

Sockets probed (`discord-ipc-0` … `-9` in each):

- `$XDG_RUNTIME_DIR/app/com.discordapp.Discord/`
- `$XDG_RUNTIME_DIR/app/com.discordapp.DiscordCanary/`
- `$XDG_RUNTIME_DIR/snap.discord/` (and Canary/PTB snaps if they exist)
- `$XDG_RUNTIME_DIR/` (native installs, or existing symlinks)

The Flatpak manifest requests access to these directories up front, so the
standard setup needs no user action.

## 8. Flatpak

- Runtime: `org.kde.Platform` 6.x + `io.qt.PySide.BaseApp`.
- Permissions (all narrow, no host escape):
  - `--socket=wayland`, `--socket=fallback-x11`, `--share=ipc`
  - `--share=network` (Discord API/CDN, Steam store/Web API)
  - `--filesystem=xdg-run/app/com.discordapp.Discord:ro` (+ Canary, snap dir)
  - `--filesystem=~/.local/share/Steam/logs:ro`
  - `--filesystem=~/.var/app/com.valvesoftware.Steam/.local/share/Steam/logs:ro`
  - `--talk-name=org.mpris.MediaPlayer2.*`
  - `--talk-name=org.kde.StatusNotifierWatcher` and
    `--own-name=org.kde.StatusNotifierItem-2-2` (tray; inside the sandbox
    the app's PID is always 2, Qt registers this name)
  - `--device=dri` (GPU rendering)

  All of these were verified from inside the `org.kde.Platform//6.11`
  runtime (E5). The session bus must not be disabled (e.g. `flatpak run
  --sandbox` breaks MPRIS and the tray).
- Autostart & running in background via the XDG **Background portal**.
- Config: `$XDG_CONFIG_HOME/rpc-buddy/config.toml`; cache (detectable index,
  images): `$XDG_CACHE_HOME/rpc-buddy/`.

## 9. GUI

- **Tray** (primary on KDE): current activity, pause toggle, module toggles,
  "Open RPC Buddy…", "Quit"; left click opens the main window.
- **Main window**: status (Discord, what is shown, pause, autostart), one box
  per module (enable toggle, health with hints, settings form generated from
  the module's `settings`), hide list ("Seen recently" / "Hidden"), "Run
  setup check…", "Quit". Closing hides it to the tray (quits if no tray).
- **Setup check** (first run, reopenable): Discord, Steam games, music, tray
  icon, autostart — coloured status and copyable `flatpak override --user …`
  commands where something is missing. The app cannot change its own sandbox
  permissions. Logic in `setup_checks.py` (Qt-free, tested).
- **Single instance**: a second launch asks the running one to show its
  window (local socket in `$XDG_RUNTIME_DIR/app/<app-id>/`).

## 10. Development workflow

- Daily work: Python venv on the host, managed with `uv`, with Python pinned
  to the version of the Flatpak runtime (host Python 3.15 may lack PySide6
  wheels).
  > **Warning:** this works because every dependency is a pip wheel. As soon
  > as we need **system packages** (e.g. a C library without wheels, distro
  > tools), switch to a **Distrobox** container instead of installing
  > things on the immutable host.
- Packaging/real-world test: `flatpak-builder` on the host (or the
  `org.flatpak.Builder` Flatpak).
- Tests: `pytest` (parsers, router, cache — no Discord needed); lint/format
  with `ruff`.

## 11. Plan

**Phase 0 — experiments (done 2026-11-19, pypresence 4.6.2)**

- **E1 ✅** Two IPC connections from one process (a game's Discord ID + rpc-buddy
  ID) work in parallel: the profile shows both cards; the game wins the
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
  A real `flatpak-builder` build follows in Phase 1.

Also verified: Discord's detectable list maps Steam games to their official
Discord app (Steam app id → Discord application id, with cover art).

**Phase 1 ✅** — core, DiscordSink, Steam module, DetectableCache, tray with
status and toggles, first Flatpak build.

**Phase 2 ✅** — MPRIS module, router rules (pause, hide list), main window,
setup check, autostart.

**Phase 3** — polish, weeks of daily use, then GitHub public, then Flathub.

## 12. Open questions

- Icon/art assets for the "rpc-buddy" Discord app (Developer Portal).
