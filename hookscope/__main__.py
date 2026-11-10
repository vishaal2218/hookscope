"""Start Hookscope: python -m hookscope (opens the browser when ready)."""

from __future__ import annotations

import json
import logging
import socket
import sys
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from . import config


def url_for(port: int) -> str:
    return f"http://{config.HOST}:{port}/"


def port_state(port: int) -> str:
    """'free', 'hookscope' (already running here) or 'other' (another app owns it)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        if s.connect_ex((config.HOST, port)) != 0:
            return "free"
    try:
        with urllib.request.urlopen(f"{url_for(port)}api/ping", timeout=2) as res:
            return "hookscope" if json.loads(res.read()).get("app") == "hookscope" else "other"
    except (OSError, ValueError):
        return "other"


def pick_port() -> tuple[int, str]:
    for port in range(config.PORT, config.PORT + config.PORT_TRIES):
        state = port_state(port)
        if state in ("free", "hookscope"):
            return port, state
    raise SystemExit(f"No free port between {config.PORT} and {config.PORT + config.PORT_TRIES - 1}.")


def open_when_ready(port: int) -> None:
    for _ in range(60):
        if port_state(port) == "hookscope":
            webbrowser.open(url_for(port))
            return
        time.sleep(0.5)


def main() -> int:
    port, state = pick_port()
    if state == "hookscope":
        print(f"Hookscope is already running. Opening {url_for(port)}")
        webbrowser.open(url_for(port))
        return 0
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if "--no-browser" not in sys.argv:
        threading.Thread(target=open_when_ready, args=(port,), daemon=True).start()
    print(f"Hookscope is running at {url_for(port)}  (close this window or press Ctrl+C to stop)")
    uvicorn.run("hookscope.app:app", host=config.HOST, port=port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
