"""Compatibility entry point for the complete Cascade workspace supervisor."""

from __future__ import annotations

import argparse
from pathlib import Path

from cascade.workspace import WorkspaceError, up


def main() -> None:
    parser = argparse.ArgumentParser(description="Cascade War Room and watchdog")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        up(args.root, host=args.host, port=args.port)
    except (WorkspaceError, ValueError) as exc:
        parser.error(str(exc))

if __name__ == "__main__":
    main()
