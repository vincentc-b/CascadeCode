from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import cascade.board.gitutil as gitutil


class _HungGit:
    def __init__(self, *_args, **_kwargs) -> None:
        self.returncode = None
        self.terminated = False
        self.killed = False

    def communicate(self, *, timeout=None):
        if not self.terminated and not self.killed:
            raise subprocess.TimeoutExpired(["git"], timeout)
        self.returncode = -15 if self.terminated else -9
        return "", ""

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


@pytest.mark.parametrize("cancelled", [False, True])
def test_bounded_git_is_reaped_on_timeout_or_cancellation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cancelled: bool
) -> None:
    process = _HungGit()
    monkeypatch.setattr(gitutil.subprocess, "Popen", lambda *_args, **_kwargs: process)
    cancel = threading.Event()
    if cancelled:
        cancel.set()

    expected = InterruptedError if cancelled else subprocess.TimeoutExpired
    with pytest.raises(expected):
        gitutil._run(
            ["status"],
            tmp_path,
            timeout=0.001,
            cancel_event=cancel,
        )

    assert process.terminated is True
    assert process.killed is False


def test_bounded_git_kills_descendant_holding_capture_pipes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "git"
    executable.write_text(
        "#!" + sys.executable + "\n"
        "import subprocess, sys\n"
        "subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)'])\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path) + os.pathsep + os.environ["PATH"])

    started = time.monotonic()
    with pytest.raises(subprocess.TimeoutExpired):
        gitutil._run(["status"], tmp_path, timeout=0.05)

    assert time.monotonic() - started < 1.0
