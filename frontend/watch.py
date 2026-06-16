"""Watch frontend source and rebuild on save (stdlib polling, no deps).

The local Ghost container bind-mounts ./theme (see docker-compose.yml), so a
rebuild lands inside the running container immediately — no `docker compose build`,
no restart. Save a file here, then refresh the browser.

Caveat: Ghost's ``{{asset}}`` helper appends a ``?v=`` version hash that only
changes when Ghost restarts, so the browser may need a hard refresh
(Ctrl/Cmd+Shift+R) to bypass cache on a CSS change. Full auto-refresh (livereload)
is a possible later addition.
"""

from __future__ import annotations

import time
from pathlib import Path

from build import ASSET_SRC, SHELL
from build import main as build_main

WATCH_PATHS = [SHELL.parent, ASSET_SRC]
POLL_SECONDS = 0.5


def snapshot() -> dict[Path, float]:
    """Map every watched source file to its mtime."""
    state: dict[Path, float] = {}
    for root in WATCH_PATHS:
        if root.exists():
            for path in root.rglob("*"):
                if path.is_file():
                    state[path] = path.stat().st_mtime
    return state


def run() -> None:
    print("Watching frontend/ for changes (Ctrl-C to stop).")
    build_main([])
    last = snapshot()
    try:
        while True:
            time.sleep(POLL_SECONDS)
            current = snapshot()
            if current != last:
                print("change detected -> rebuilding")
                build_main([])
                last = current
    except KeyboardInterrupt:
        print("\nstopped.")


if __name__ == "__main__":
    run()
