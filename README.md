# RPC Buddy

Shows what you play and listen to on Linux as your Discord activity —
built for setups where Discord runs as a Flatpak and cannot detect games
itself.

**Status:** early development. Not on Flathub yet; build it locally (see below).

## Features

- **Steam games** appear as "Playing …" with the game's official Discord
  name and artwork, as if Discord had detected the game itself.
- **Music** from MPRIS players appears as "Listening to …" — e.g. Deezer,
  TIDAL or YouTube Music (also in a browser), Elisa, Rhythmbox, Strawberry
  and other music players. Spotify is optional: the setup check asks whether
  your Spotify account is linked to Discord (then Discord shows it itself);
  if not, RPC Buddy shows it.
- Game and music are shown **side by side**; the game wins the status line
  next to your name.
- **Main window** shows what's on Discord right now, like Discord's own
  activity cards — with **Hide** on each card for games or music sources you
  want to keep private. Follows your desktop's light/dark theme.
- **Tray icon** (KDE Plasma and other desktops with a system tray) with the
  current activity, pause and module switches. Closing the window keeps RPC
  Buddy running there; **Quit** in the window or tray menu stops it.
- **Setup check** on first start: shows what was found and gives copyable
  commands for anything missing.
- **Starts with your desktop session**, quietly in the tray (can be switched
  off).

## Requirements

- Linux desktop with Flatpak (tested on KDE Plasma; GNOME should work, without
  a tray icon unless the AppIndicator extension is installed — not tested yet)
- The official Discord client — the Flatpak `com.discordapp.Discord` works
  out of the box; Canary and Snap should as well (untested). A Discord installed without
  Flatpak needs one extra permission (see Troubleshooting).
- Steam (native or Flatpak) for game detection

## Install a test build

If you got a `rpc-buddy.flatpak` file:

```bash
flatpak install --user rpc-buddy.flatpak
```

A newer file is installed the same way and replaces the old version.

## Install (local build)

```bash
flatpak install --user flathub org.kde.Sdk//6.11 io.qt.PySide.BaseApp//6.11
flatpak-builder --user --install --force-clean build-dir \
    flatpak/io.github.YetAnotherGerrit.RpcBuddy.yml
flatpak run io.github.YetAnotherGerrit.RpcBuddy
```

On the first start, the setup check opens. Close it with **Done**, and RPC
Buddy starts automatically from then on.

## How it works

| What | How |
|---|---|
| Running Steam game | Read from Steam's own log file (`logs/console_log.txt`), read-only. No Steam account, API key or network access needed. |
| Game name and artwork | Discord's public list of games it can detect, downloaded at most once a day and cached. |
| Music | Read from the MPRIS interface that music players offer on the desktop session bus. |
| Showing it on Discord | Sent only to the Discord client running on your computer, over its local connection (IPC). |

### Privacy

RPC Buddy has no servers and no tracking. It only connects to:

- Discord's public game list (at most once a day),
- Discord's image server, to show game covers in its window,
- cover images that your music player itself provides as web links, to show
  them in its window (Discord loads them as well, to show them to your
  friends).

Your configuration stays in
`~/.var/app/io.github.YetAnotherGerrit.RpcBuddy/config/rpc-buddy/config.toml`.

## Limitations

- Games that Discord doesn't know are not shown.
- Music cover art only appears if the player provides it as a web link;
  browsers usually only provide a local file, which Discord can't show.
- Only the official Discord clients are supported.

## Troubleshooting

Open the main window (tray icon, or start RPC Buddy again) and click
**Run setup check…**. Common cases:

- **Discord installed without Flatpak** (e.g. .deb, .rpm, AUR): allow access
  to its socket once, then restart RPC Buddy. Start Discord before RPC Buddy.

  ```bash
  flatpak override --user --filesystem=xdg-run/discord-ipc-0 io.github.YetAnotherGerrit.RpcBuddy
  ```

- **Steam installed in an unusual place**: allow RPC Buddy to read Steam's
  logs folder:

  ```bash
  flatpak override --user --filesystem=/path/to/Steam/logs:ro io.github.YetAnotherGerrit.RpcBuddy
  ```

- **Logs**: run `flatpak run io.github.YetAnotherGerrit.RpcBuddy --debug` in a
  terminal.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                               # .venv with Python 3.13 and all dependencies
uv run rpc-buddy                      # run with window and tray icon
uv run rpc-buddy --headless --debug   # run without GUI, verbose logging
uv run pytest                         # tests
uv run ruff check . && uv run ruff format --check .
```

Create a single-file bundle for testers (see DESIGN.md §8.3):

```bash
flatpak-builder --repo=repo --force-clean build-dir flatpak/io.github.YetAnotherGerrit.RpcBuddy.yml
flatpak build-bundle repo rpc-buddy.flatpak io.github.YetAnotherGerrit.RpcBuddy \
    --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo
```

The design, decisions and test results are in [DESIGN.md](DESIGN.md);
ideas for later in [FUTURE_IDEAS.md](FUTURE_IDEAS.md). New sources are
added as modules — see `src/rpc_buddy/module.py`.

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
