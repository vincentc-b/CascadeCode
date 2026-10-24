"""``cascade probe`` operator entry (feat_012_003)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from cascade.probe.errors import ProbeError, ProbeTimeoutError
from cascade.probe.harness import probe_workspace, smoke_probe_harness


def register_probe_parser(subparsers: argparse._SubParsersAction) -> None:
    probe = subparsers.add_parser(
        "probe",
        help="Disposable lifecycle readiness probe workspace harness",
    )
    probe_sub = probe.add_subparsers(dest="probe_command", required=True)

    prepare = probe_sub.add_parser(
        "prepare",
        help="Allocate a disposable git workspace and initialized board",
    )
    prepare.add_argument(
        "--debug-retain",
        action="store_true",
        help="Keep the workspace on disk after a successful prepare (debug only)",
    )
    prepare.add_argument(
        "--parent",
        type=Path,
        default=None,
        help="Directory that will contain the new workspace (default: system temp)",
    )
    prepare.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON object on stdout",
    )

    run = probe_sub.add_parser(
        "run",
        help="Exercise synthetic lifecycle success and stall scenarios",
    )
    run.add_argument(
        "--parent",
        type=Path,
        default=None,
        help="Directory that will contain the new workspace (default: system temp)",
    )
    run.add_argument(
        "--debug-retain",
        action="store_true",
        help="Keep the workspace on disk after the run (debug only)",
    )
    run.add_argument(
        "--json",
        action="store_true",
        help="Emit a single JSON object on stdout",
    )


def run_probe_command(args: argparse.Namespace) -> None:
    if args.probe_command == "prepare":
        _run_prepare(args)
        return
    if args.probe_command == "run":
        _run_lifecycle(args)
        return
    raise SystemExit(f"unknown probe command: {args.probe_command!r}")


def _run_prepare(args: argparse.Namespace) -> None:
    try:
        if args.debug_retain:
            workspace = smoke_probe_harness(
                retain_artifacts=True,
                parent_dir=args.parent,
            )
            payload = {
                "ok": True,
                "workspace": str(workspace.root),
                "retained": True,
            }
        else:
            with probe_workspace(parent_dir=args.parent) as workspace:
                workspace.deadline.check(phase="probe prepare")
                board = workspace.root / "docs" / "tasks" / "1_backlog"
                if not board.is_dir():
                    raise ProbeError(f"missing board column: {board}")
                payload = {"ok": True, "workspace": str(workspace.root), "retained": False}
    except (ProbeError, ProbeTimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(payload))
    else:
        print(f"probe workspace ok ({payload['workspace']})")


def _run_lifecycle(args: argparse.Namespace) -> None:
    from cascade.probe.lifecycle import run_lifecycle_probe

    try:
        if args.debug_retain:
            workspace = smoke_probe_harness(
                retain_artifacts=True,
                parent_dir=args.parent,
            )
            report = run_lifecycle_probe(workspace)
            payload = {
                "ok": report.ok,
                "failing_phase": report.failing_phase,
                "phases": report.to_dict()["phases"],
                "workspace": str(workspace.root),
                "retained": True,
            }
        else:
            with probe_workspace(parent_dir=args.parent) as workspace:
                report = run_lifecycle_probe(workspace)
                payload = {
                    "ok": report.ok,
                    "failing_phase": report.failing_phase,
                    "phases": report.to_dict()["phases"],
                    "workspace": str(workspace.root),
                    "retained": False,
                }
    except (ProbeError, ProbeTimeoutError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc

    if args.json:
        print(json.dumps(payload))
    else:
        status = "ok" if payload["ok"] else "failed"
        phase = payload.get("failing_phase") or "none"
        print(f"probe lifecycle {status} (failing_phase={phase})")
    if not payload["ok"]:
        raise SystemExit(1)
