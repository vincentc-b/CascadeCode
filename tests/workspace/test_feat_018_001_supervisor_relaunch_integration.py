"""Integration: launcher relaunches worker on source edit (feat_018_001 / task_018_001_003)."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from cascade.workspace import init_workspace
from tests.support import make_git_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _seed_trunk_commit(root: Path) -> None:
    (root / "README.md").write_text("workspace\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "init board")


def _wait_for_http(url: str, *, timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
            time.sleep(0.05)
    raise AssertionError(f"server did not respond at {url}: {last_error}")


def _cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode(errors="replace").strip()


def _direct_child_pids(parent: int) -> list[int]:
    children: list[int] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            stat = (entry / "stat").read_text()
        except OSError:
            continue
        rparen = stat.rfind(")")
        if rparen == -1:
            continue
        rest = stat[rparen + 2 :].split()
        if len(rest) < 2:
            continue
        if int(rest[1]) == parent:
            children.append(pid)
    return children


def _worker_pid_for_launcher(launcher_pid: int) -> int | None:
    for pid in _direct_child_pids(launcher_pid):
        if "cascade.workspace.worker" in _cmdline(pid):
            return pid
    return None


def _read_supervisor_lock_pid(root: Path) -> int:
    text = (root / ".cascade" / "supervisor.lock").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("pid="):
            return int(line.split("=", 1)[1].strip())
    raise AssertionError(f"supervisor.lock missing pid= line: {text!r}")


def _copy_cascade_for_subprocess(tmp_path: Path) -> Path:
    """Copy ``cascade/`` so subprocess edits do not mutate the dev tree."""

    repo_root = Path(__file__).resolve().parents[2]
    install_root = tmp_path / "cascade_install"
    shutil.copytree(
        repo_root / "cascade",
        install_root / "cascade",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    up_py = install_root / "cascade" / "workspace" / "up.py"
    up_text = up_py.read_text(encoding="utf-8")
    up_text = up_text.replace(
        "_SOURCE_CHECK_INTERVAL_SECONDS = 1.0",
        "_SOURCE_CHECK_INTERVAL_SECONDS = 0.05",
    )
    up_py.write_text(up_text, encoding="utf-8")
    return install_root


def _process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def test_subprocess_up_relaunches_worker_and_sweeps_worktree_index_lock(
    tmp_path: Path,
) -> None:
    root = make_git_repo(tmp_path)
    init_workspace(root)
    _seed_trunk_commit(root)

    install_root = _copy_cascade_for_subprocess(tmp_path)
    touch_target = install_root / "cascade" / "relaunch_probe.py"
    touch_target.write_text("PROBE = 1\n", encoding="utf-8")

    port = _free_port()
    subprocess_cwd = tmp_path / "subprocess_cwd"
    subprocess_cwd.mkdir()
    env = os.environ.copy()
    # Avoid importing the dev tree's ``cascade/`` from pytest's working directory.
    env["PYTHONPATH"] = str(install_root)

    launcher = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "cascade.cli",
            "up",
            "--root",
            str(root),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=subprocess_cwd,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    worker_after: int | None = None
    worker_before: int | None = None
    try:
        _wait_for_http(f"{base}/api/board")
        launcher_pid = launcher.pid
        lock_pid = _read_supervisor_lock_pid(root)
        assert lock_pid == launcher_pid

        worker_before = _worker_pid_for_launcher(launcher_pid)
        assert worker_before is not None

        planted_wt = root / ".cascade" / "worktrees" / "task_planted"
        planted_wt.mkdir(parents=True)
        planted_lock = planted_wt / ".git" / "index.lock"
        planted_lock.parent.mkdir(parents=True)
        planted_lock.write_text("stale\n", encoding="utf-8")

        connect_ok = threading.Event()
        connect_refused = threading.Event()

        def connect_during_restart() -> None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(45.0)
            try:
                sock.connect(("127.0.0.1", port))
                connect_ok.set()
            except ConnectionRefusedError:
                connect_refused.set()
            finally:
                sock.close()

        connector = threading.Thread(target=connect_during_restart, daemon=True)
        connector.start()
        time.sleep(0.05)
        touch_target.write_text("PROBE = 2\n", encoding="utf-8")
        # Also touch an existing module so the fingerprint definitely changes.
        init_py = install_root / "cascade" / "__init__.py"
        init_py.write_text(init_py.read_text(encoding="utf-8") + "\n", encoding="utf-8")

        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            worker_after = _worker_pid_for_launcher(launcher_pid)
            if (
                worker_after is not None
                and worker_after != worker_before
                and not planted_lock.is_file()
            ):
                break
            time.sleep(0.05)
        else:
            raise AssertionError(
                "worker did not relaunch or stale index.lock was not swept"
            )

        connector.join(timeout=5.0)
        assert connect_refused.is_set() is False
        assert connect_ok.is_set()

        assert launcher.pid == launcher_pid
        assert _read_supervisor_lock_pid(root) == launcher_pid
        assert worker_after != worker_before

        _wait_for_http(f"{base}/api/board")
        with urllib.request.urlopen(f"{base}/api/board") as resp:
            json.loads(resp.read().decode())
    finally:
        launcher.send_signal(signal.SIGTERM)
        stderr = launcher.communicate(timeout=60)[1]
        assert launcher.returncode == 0, stderr

    assert not _process_exists(worker_before)
    if worker_after is not None:
        assert not _process_exists(worker_after)
