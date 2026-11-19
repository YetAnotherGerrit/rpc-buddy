"""Command-line entry point."""

import argparse
import contextlib
import logging
import signal
import sys

from rpc_buddy import APP_ID, APP_NAME, __version__
from rpc_buddy.config import Config
from rpc_buddy.engine import Engine, EngineState
from rpc_buddy.setup_checks import detect_environment

log = logging.getLogger("rpc_buddy")


def _describe(state: EngineState) -> str:
    shown = ", ".join(m.summary for m in state.shown) or "nothing"
    modules = ", ".join(
        f"{m.name}: {m.health.state.value} {m.health.message}".strip() for m in state.modules
    )
    paused = " (paused)" if state.paused else ""
    return f"showing {shown}{paused} | {state.discord.message} | {modules}"


def run_headless(config: Config) -> int:
    last = ""

    def on_state(state: EngineState) -> None:
        nonlocal last
        text = _describe(state)
        if text != last:
            last = text
            log.info("%s", text)

    engine = Engine(config, on_state=on_state)
    with contextlib.suppress(KeyboardInterrupt):
        engine.run_forever()
    return 0


def run_gui(config: Config, background: bool) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from rpc_buddy.gui.setup import SetupDialog
    from rpc_buddy.gui.single import InstanceServer, notify_running_instance
    from rpc_buddy.gui.tray import EngineBridge, Tray, app_icon
    from rpc_buddy.gui.window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("rpc-buddy")
    app.setApplicationDisplayName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(app_icon())
    app.setQuitOnLastWindowClosed(False)

    if notify_running_instance():
        log.info("Already running, showing the existing window")
        return 0
    instance = InstanceServer()

    has_tray = Tray.available()
    if not has_tray:
        log.warning("No system tray available, closing the window quits RPC Buddy")

    bridge = EngineBridge()
    engine = Engine(config, on_state=bridge.state_changed.emit)
    setup = SetupDialog(
        None,
        environment=lambda: detect_environment(has_tray),
        on_done=engine.set_setup_done,
        set_spotify_answer=lambda answer: engine.set_module_settings(
            "mpris", {"include_spotify": answer == "via_buddy", "spotify_answer": answer}
        ),
    )

    def open_setup() -> None:
        setup.show()
        setup.raise_()
        setup.activateWindow()

    window = MainWindow(engine, quit_app=app.quit, keep_running=has_tray, open_setup=open_setup)
    tray = Tray(engine, open_window=window.show_and_raise, quit_app=app.quit)
    bridge.state_changed.connect(window.on_state)
    bridge.state_changed.connect(tray.on_state)
    bridge.state_changed.connect(setup.on_state)
    instance.show_requested.connect(window.show_and_raise)

    first_run = not config.setup_done
    engine.start_in_thread()
    app.aboutToQuit.connect(engine.stop)
    if not (background and has_tray):
        window.show_and_raise()
    if first_run:
        # Give the modules a moment to report their status before showing it.
        QTimer.singleShot(1500, open_setup)

    # Let Python handle Ctrl+C while Qt's event loop is running.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(500)

    return app.exec()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rpc-buddy", description=APP_NAME)
    parser.add_argument("--headless", action="store_true", help="run without GUI")
    parser.add_argument(
        "--background", action="store_true", help="start in the tray without opening the window"
    )
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if not args.debug:
        logging.getLogger("asyncio").setLevel(logging.WARNING)

    config = Config.load()
    log.info("%s %s, config: %s", APP_NAME, __version__, config.path)
    return run_headless(config) if args.headless else run_gui(config, args.background)
