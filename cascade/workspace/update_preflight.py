"""Validate a pending source update in a throwaway subprocess (feat_018_003)."""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PREFLIGHT_TIMEOUT_S = 30.0
_STDERR_TAIL_MAX = 8000

_PREFLIGHT_MODULE = "cascade.workspace.update_preflight"


@dataclass(frozen=True)
class UpdatePreflightResult:
    ok: bool
    exit_code: int | None
    stderr_tail: str
    message: str


def cascade_source_parent() -> Path:
    """Directory that must be on ``PYTHONPATH`` to load Cascade from disk."""

    return Path(__file__).resolve().parents[2]


def _bounded_tail(text: str, *, limit: int = _STDERR_TAIL_MAX) -> str:
    if len(text) <= limit:
        return text
    return text[-limit:]


def run_update_preflight(
    workspace_root: Path,
    *,
    timeout: float = PREFLIGHT_TIMEOUT_S,
) -> UpdatePreflightResult:
    """Import entry modules from the current disk source and run ``prepare_up``."""

    root = Path(workspace_root).resolve()
    env = os.environ.copy()
    parent = str(cascade_source_parent())
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        parent
        if not current_pythonpath
        else os.pathsep.join((parent, current_pythonpath))
    )
    try:
        completed = subprocess.run(
            [sys.executable, "-m", _PREFLIGHT_MODULE, str(root)],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        combined = (exc.stdout or "") + (exc.stderr or "")
        return UpdatePreflightResult(
            ok=False,
            exit_code=None,
            stderr_tail=_bounded_tail(combined),
            message=f"update preflight timed out after {timeout:.0f}s",
        )
    combined = completed.stdout + completed.stderr
    tail = _bounded_tail(combined)
    if completed.returncode == 0:
        return UpdatePreflightResult(
            ok=True,
            exit_code=0,
            stderr_tail=tail,
            message="ok",
        )
    message = tail.strip().splitlines()[-1] if tail.strip() else f"exit {completed.returncode}"
    return UpdatePreflightResult(
        ok=False,
        exit_code=completed.returncode,
        stderr_tail=tail,
        message=message,
    )


def _preflight_main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print(
            f"usage: python -m {_PREFLIGHT_MODULE} WORKSPACE_ROOT",
            file=sys.stderr,
        )
        return 2
    import cascade.cli  # noqa: F401 — entry import from new source on disk
    from cascade.workspace.up import prepare_up

    prepare_up(Path(args[0]))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(_preflight_main())
    except SystemExit:
        raise
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from exc
