# Contributing to RPC Buddy

Thanks for your interest! RPC Buddy is a small project; bug reports, ideas and
pull requests are welcome.

## Reporting a bug

Open an [issue](https://github.com/YetAnotherGerrit/rpc-buddy/issues) and include:

- your desktop (e.g. KDE Plasma, GNOME) and how Discord and Steam are installed
  (Flatpak or not),
- what the setup check shows (main window → **Run setup check…**),
- if possible, the output of
  `flatpak run io.github.YetAnotherGerrit.RpcBuddy --debug`.

The debug output can contain game names, song titles and file paths — please
look through it and remove anything you don't want to share.

## Development setup

You need [uv](https://docs.astral.sh/uv/):

```bash
uv sync                 # Python 3.13 and all dependencies in .venv
uv run rpc-buddy        # run the app
uv run pytest           # tests
uv run ruff check . && uv run ruff format --check .
```

Building and installing the Flatpak is described in the [README](README.md);
the design and the reasons behind decisions are in [DESIGN.md](DESIGN.md).

## Ground rules

- **Tests and lint must pass** — GitHub runs them on every push and pull request.
- **Only made-up content** in tests, docs and screenshots: no real game or song
  titles, no real Steam/Discord IDs, no real play times.
- **Privacy first:** RPC Buddy has no servers and no tracking. New network
  requests or sandbox permissions need a good reason — please discuss them in
  an issue first.
- **Text from outside is plain text:** titles and artists can come from
  websites; never render them as HTML (see DESIGN.md §13).
- **Keep the docs current:** update the README (and DESIGN.md where it
  describes behaviour) in the same pull request.
- New sources (launchers, players, …) are added as modules — see
  `src/rpc_buddy/module.py`.

By contributing, you agree that your contribution is licensed under
GPL-3.0-or-later, like the rest of the project.
