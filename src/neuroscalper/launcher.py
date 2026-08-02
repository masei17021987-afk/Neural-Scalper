from __future__ import annotations

import atexit
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

import uvicorn

from . import __version__
from .paths import DATA_DIR, ensure_runtime_dirs


def _health_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{browser_host}:{port}/health"


def _app_url(host: str, port: int) -> str:
    browser_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    return f"http://{browser_host}:{port}/"


def _is_our_server(host: str, port: int) -> bool:
    try:
        with urllib.request.urlopen(_health_url(host, port), timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return bool(payload.get("ok"))
    except (OSError, ValueError, urllib.error.URLError):
        return False


def _port_in_use(host: str, port: int) -> bool:
    probe_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((probe_host, port)) == 0


def _open_when_ready(host: str, port: int) -> None:
    for _ in range(80):
        if _is_our_server(host, port):
            webbrowser.open(_app_url(host, port), new=2)
            return
        time.sleep(0.25)


def main() -> int:
    ensure_runtime_dirs()
    host = os.getenv("NEUROSCALPER_HOST", "127.0.0.1")
    port = int(os.getenv("NEUROSCALPER_PORT", "8094"))
    if _is_our_server(host, port):
        print("CryptoHunter Neural Scalper уже запущен. Открываю интерфейс…")
        webbrowser.open(_app_url(host, port), new=2)
        return 0
    if _port_in_use(host, port):
        print(f"Порт {port} занят другой программой.")
        print("Измените NEUROSCALPER_PORT или закройте процесс, занявший порт.")
        return 2

    pid_file = DATA_DIR / "server.pid"
    pid_file.write_text(str(os.getpid()), encoding="utf-8")

    def cleanup() -> None:
        try:
            if pid_file.exists() and pid_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
                pid_file.unlink()
        except OSError:
            pass

    atexit.register(cleanup)
    threading.Thread(target=_open_when_ready, args=(host, port), daemon=True).start()
    print("=" * 62)
    print(f" CryptoHunter Neural Scalper {__version__}")
    print(" Локальный интерфейс:", _app_url(host, port))
    print(" Реальные ордера: ЗАБЛОКИРОВАНЫ")
    print(" Для завершения закройте это окно или нажмите Ctrl+C.")
    print("=" * 62)
    try:
        uvicorn.run(
            "neuroscalper.web.api:app",
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
