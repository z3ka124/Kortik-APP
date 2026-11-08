# c:\Kortik\Kortik-Listener-App\app\main.py
"""
Ulazna tacka aplikacije.

Redosled:
  1. putanje + logovi (sa redakcijom tajni)
  2. single-instance (QLocalServer)
  3. UI + async runner
  4. provera ažuriranja se pokreće iz MainWindow-a

Pokretanje:
    python -m app.main
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path


def _ensure_root_on_path() -> None:
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))


def main() -> int:
    _ensure_root_on_path()

    try:
        from PySide6.QtNetwork import QLocalServer, QLocalSocket
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("PySide6 nije instaliran. Pokreni:  pip install -r requirements.txt")
        return 2

    from app.auth.device_flow import DeviceFlow
    from app.config import AppPaths, load_settings
    from app.logs import setup_logging
    from app.net.api import ListenerApi
    from app.security.storage import SecretStore
    from app.ui.async_runner import AsyncRunner
    from app.ui.main_window import MainWindow
    from app.version import API_BASE_URL, APP_NAME, APP_VERSION

    paths = AppPaths.build().ensure()
    logger = setup_logging(paths.logs)
    logger.info("%s %s — start (data=%s)", APP_NAME, APP_VERSION, paths.root)

    settings = load_settings(paths)
    base_url = (settings.api_base_url or "").strip() or API_BASE_URL

    try:
        from app.system.autostart import sync as sync_autostart

        sync_autostart(settings.autostart)
    except Exception as e:
        logger.debug("Autostart sync preskočen: %s", e)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setQuitOnLastWindowClosed(True)

    server_name = "kortik-listener-single-instance"
    probe = QLocalSocket()
    probe.connectToServer(server_name)
    if probe.waitForConnected(300):
        logger.info("Aplikacija je već pokrenuta — izlazim.")
        probe.disconnectFromServer()
        return 0
    probe.abort()

    QLocalServer.removeServer(server_name)
    server = QLocalServer()
    if not server.listen(server_name):
        logger.warning("Single-instance server nije otvoren: %s", server.errorString())

    store = SecretStore(paths.secrets)
    api = ListenerApi(base_url)
    flow = DeviceFlow(api, store)
    runner = AsyncRunner()

    logger.info("API: %s | secrets: %s", base_url, "DPAPI" if store.is_available() else "NEDOSTUPNO")

    window = MainWindow(paths, settings, api, store, flow, runner, logger)
    if settings.start_minimized:
        window.showMinimized()
    else:
        window.show()

    exit_code = app.exec()

    try:
        asyncio.run_coroutine_threadsafe(api.close(), runner.loop).result(timeout=3)
    except Exception:
        pass
    runner.stop()
    server.close()
    logger.info("Izlaz (code=%s)", exit_code)
    return int(exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
