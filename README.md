# RPC Buddy

Shows what you play and listen to on Linux as Discord Rich Presence — built
for setups where Discord runs as a Flatpak and cannot detect games itself.

**Status:** early development, not ready for use yet.

- Steam games appear with their official Discord name and artwork
- Runs as a Flatpak, with a tray icon on KDE Plasma
- Modular: more sources (e.g. music players via MPRIS) are planned

See [DESIGN.md](DESIGN.md) for the design and [FUTURE_IDEAS.md](FUTURE_IDEAS.md)
for ideas that are not part of the first version.

## Development

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync                 # create .venv with Python 3.13 and all dependencies
uv run rpc-buddy        # run with tray icon
uv run rpc-buddy --headless --debug   # run without GUI, verbose logging
uv run pytest           # tests
uv run ruff check .     # lint
```

Build and install the Flatpak locally:

```bash
flatpak-builder --user --install --force-clean build-dir \
    flatpak/io.github.YetAnotherGerrit.RpcBuddy.yml
flatpak run io.github.YetAnotherGerrit.RpcBuddy
```

## License

GPL-3.0-or-later, see [LICENSE](LICENSE).
