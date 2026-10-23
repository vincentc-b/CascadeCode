"""Shared ``cascade up`` subprocess harness for feat_018 integration tests."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from cascade.workspace import init_workspace

_DRAIN_TEST_TOML = """\
task_parallelism = 4

[worker]
drain_seconds = 2

[automation]
enabled = false
poll_seconds = 999

[providers]
default = "fake"

[providers.fake]
epic = "fast"
feature = "fast"
task = "fast"

[providers.fake.roles]
epic_architect = "drain-replay"
"""


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def seed_trunk_commit(root: Path) -> None:
    (root / "README.md").write_text("workspace\n", encoding="utf-8")
    git(root, "add", "README.md")
    git(root, "commit", "-m", "init board")


def write_drain_test_config(root: Path) -> None:
    (root / "cascade.toml").write_text(_DRAIN_TEST_TOML, encoding="utf-8")


def prepare_drain_test_repo(tmp_path: Path) -> Path:
    """Git workspace with drain-test ``cascade.toml`` (board docs must be committed before ``up``)."""

    from tests.support import make_git_repo, write_role_skill_fixtures

    root = make_git_repo(tmp_path)
    init_workspace(root)
    write_role_skill_fixtures(root)
    write_drain_test_config(root)
    seed_trunk_commit(root)
    return root


def wait_for_http(url: str, *, timeout: float = 30.0) -> None:
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


def http_get(url: str) -> tuple[int, dict[str, str], bytes]:
    with urllib.request.urlopen(url) as resp:
        headers = {k.lower(): v for k, v in resp.headers.items()}
        return resp.status, headers, resp.read()


def get_supervisor_health(base: str) -> tuple[int, dict | None]:
    """Fetch ``GET /api/health`` for feat_018_003 integration assertions."""

    status, _, raw = http_get(f"{base}/api/health")
    payload = json.loads(raw.decode())
    if payload is not None and not isinstance(payload, dict):
        raise AssertionError(f"unexpected /api/health payload: {payload!r}")
    return status, payload


def http_post_json(
    url: str,
    payload: dict | None = None,
    *,
    expect_error: bool = False,
) -> tuple[int, dict[str, str], dict]:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as resp:
            headers = {k.lower(): v for k, v in resp.headers.items()}
            body = json.loads(resp.read().decode())
            return resp.status, headers, body
    except urllib.error.HTTPError as exc:
        headers = {k.lower(): v for k, v in exc.headers.items()}
        body = json.loads(exc.read().decode())
        if not expect_error:
            raise
        return exc.code, headers, body


def cmdline(pid: int) -> str:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except OSError:
        return ""
    return raw.replace(b"\x00", b" ").decode(errors="replace").strip()


def direct_child_pids(parent: int) -> list[int]:
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


def worker_pid_for_launcher(launcher_pid: int) -> int | None:
    for pid in direct_child_pids(launcher_pid):
        if "cascade.workspace.worker" in cmdline(pid):
            return pid
    return None


def copy_cascade_for_subprocess(tmp_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    install_root = tmp_path / "cascade_install"
    shutil.copytree(
        repo_root / "cascade",
        install_root / "cascade",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    routes_src = Path(__file__).resolve().parent / "drain_integration_routes.py"
    shutil.copy2(
        routes_src,
        install_root / "cascade" / "war_room" / "drain_integration_routes.py",
    )
    server_py = install_root / "cascade" / "war_room" / "server.py"
    server_text = server_py.read_text(encoding="utf-8")
    hook = (
        "\nfrom cascade.war_room.drain_integration_routes import install as _install_drain_routes\n"
        "_install_drain_routes()\n"
    )
    if "_install_drain_routes()" not in server_text:
        server_py.write_text(server_text + hook, encoding="utf-8")
    up_py = install_root / "cascade" / "workspace" / "up.py"
    up_text = up_py.read_text(encoding="utf-8")
    up_text = up_text.replace(
        "_SOURCE_CHECK_INTERVAL_SECONDS = 1.0",
        "_SOURCE_CHECK_INTERVAL_SECONDS = 0.05",
    )
    up_py.write_text(up_text, encoding="utf-8")
    return install_root


def touch_cascade_source(install_root: Path) -> None:
    init_py = install_root / "cascade" / "__init__.py"
    init_py.write_text(init_py.read_text(encoding="utf-8") + "\n", encoding="utf-8")


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def poll_until(predicate, *, timeout: float = 30.0, interval: float = 0.05) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError("condition not met before timeout")


@dataclass
class CascadeUpProcess:
    launcher: subprocess.Popen[str]
    root: Path
    install_root: Path
    port: int
    env: dict[str, str]
    stderr_path: Path
    stderr_stream: TextIO

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def worker_pid(self) -> int | None:
        assert self.launcher.pid is not None
        return worker_pid_for_launcher(self.launcher.pid)

    def stop(self) -> str:
        self.launcher.send_signal(signal.SIGTERM)
        try:
            self.launcher.wait(timeout=60)
        except subprocess.TimeoutExpired:
            self.launcher.kill()
            self.launcher.wait(timeout=10)
        finally:
            self.stderr_stream.close()
        return self.stderr_path.read_text(encoding="utf-8")


def start_cascade_up_on_root(
    tmp_path: Path,
    root: Path,
    *,
    extra_env: dict[str, str] | None = None,
    enable_drain_routes: bool = False,
) -> CascadeUpProcess:
    install_root = copy_cascade_for_subprocess(tmp_path)
    port = free_port()
    subprocess_cwd = tmp_path / "subprocess_cwd"
    subprocess_cwd.mkdir(exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(install_root)
    env["CASCADE_ENABLE_FAKE_PROVIDER"] = "1"
    if extra_env:
        env.update(extra_env)
    if enable_drain_routes:
        env["CASCADE_DRAIN_INTEGRATION"] = "1"

    stderr_path = tmp_path / "cascade_up.stderr.log"
    stderr_stream = stderr_path.open("w", encoding="utf-8")
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
        stderr=stderr_stream,
        text=True,
    )
    proc = CascadeUpProcess(
        launcher=launcher,
        root=root,
        install_root=install_root,
        port=port,
        env=env,
        stderr_path=stderr_path,
        stderr_stream=stderr_stream,
    )
    wait_for_http(f"{proc.base}/api/board")
    return proc


def start_cascade_up(
    tmp_path: Path,
    *,
    extra_env: dict[str, str] | None = None,
    enable_drain_routes: bool = False,
) -> CascadeUpProcess:
    root = prepare_drain_test_repo(tmp_path)
    return start_cascade_up_on_root(
        tmp_path,
        root,
        extra_env=extra_env,
        enable_drain_routes=enable_drain_routes,
    )


def wait_for_worker_relaunch(proc: CascadeUpProcess, previous_worker: int) -> int:
    relaunched: int | None = None

    def _relaunched() -> bool:
        nonlocal relaunched
        relaunched = proc.worker_pid
        return relaunched is not None and relaunched != previous_worker

    poll_until(_relaunched, timeout=45.0)
    assert relaunched is not None
    wait_for_http(f"{proc.base}/api/board")
    return relaunched


def poll_updating_post(base: str, *, timeout: float = 30.0) -> tuple[int, dict[str, str], dict]:
    deadline = time.monotonic() + timeout
    last: tuple[int, dict[str, str], dict] | None = None
    while time.monotonic() < deadline:
        status, headers, body = http_post_json(
            f"{base}/api/activate_epic",
            {"id": "epic_missing_probe"},
            expect_error=True,
        )
        last = (status, headers, body)
        if status == 503 and body.get("error") == "updating":
            connection = headers.get("connection", "")
            if connection.lower() == "close":
                return status, headers, body
        time.sleep(0.05)
    raise AssertionError(f"never saw 503 updating with Connection: close; last={last}")
