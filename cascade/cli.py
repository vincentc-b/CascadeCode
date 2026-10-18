"""Cascade operator CLI (`cascade init`, `cascade up` in later tasks)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cascade.workspace import WorkspaceError, init_workspace, up


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="cascade")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Scaffold board layout in a git repo")
    init_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Git workspace root (default: current directory)",
    )

    up_parser = subparsers.add_parser("up", help="Start War Room and watchdog on the product trunk")
    up_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Git workspace root (default: current directory)",
    )
    up_parser.add_argument("--host", default="127.0.0.1", help="Loopback bind address")
    up_parser.add_argument("--port", type=int, default=8765, help="HTTP port")

    args = parser.parse_args(argv)

    if args.command == "init":
        try:
            init_workspace(args.root if args.root is not None else Path.cwd())
        except WorkspaceError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        return

    if args.command == "up":
        try:
            up(
                args.root if args.root is not None else Path.cwd(),
                host=args.host,
                port=args.port,
            )
        except (WorkspaceError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        return


if __name__ == "__main__":
    main()
