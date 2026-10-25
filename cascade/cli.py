"""Cascade operator CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from cascade.board.errors import BoardError
from cascade.cancellation import cancel_work_item
from cascade.probe.cli import register_probe_parser, run_probe_command
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

    cancel_parser = subparsers.add_parser(
        "cancel", help="Cancel an epic, feature, or task"
    )
    cancel_parser.add_argument("work_id", help="Epic, feature, or task id")
    cancel_parser.add_argument(
        "--reason", required=True, help="Why the work is being cancelled"
    )
    cancel_parser.add_argument(
        "--discard-uncommitted",
        action="store_true",
        help="Confirm discard of uncommitted changes owned by this cancellation",
    )
    cancel_parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Git workspace root (default: current directory)",
    )

    register_probe_parser(subparsers)
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

    if args.command == "probe":
        run_probe_command(args)
        return

    if args.command == "cancel":
        try:
            result = cancel_work_item(
                args.work_id,
                args.reason,
                root=args.root if args.root is not None else Path.cwd(),
                discard_uncommitted=args.discard_uncommitted,
            )
        except BoardError as exc:
            print(str(exc), file=sys.stderr)
            raise SystemExit(1) from exc
        if not result.complete:
            print(
                f"{result.work_id}: cancelling; cleanup failed at "
                f"{result.cleanup_step}: {result.cleanup_error}",
                file=sys.stderr,
            )
            raise SystemExit(1)
        state = "cancelled" if result.changed else "already cancelled"
        print(f"{result.work_id}: {state}")
        return


if __name__ == "__main__":
    main()
