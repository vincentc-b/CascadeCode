"""Signed deployment bootstrap and real loaded-worker evidence."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

import pytest

from cascade.watchdog.capabilities import default_capability_registry
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.runtime_identity import (
    validate_loaded_runtime_identity,
    verify_loaded_runtime_identity,
)
from cascade.workspace.source_fingerprint import source_fingerprint
from cascade.workspace.supervisor_status import utc_now_iso
from tests.harness.cascade_up_subprocess import (
    free_port,
    get_supervisor_health,
    poll_until,
    prepare_drain_test_repo,
    wait_for_http,
    worker_pid_for_launcher,
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _digest(value: dict[str, object]) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(body).hexdigest()


def _sign(value: dict[str, object], key: bytes) -> str:
    body = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hmac.new(key, body, hashlib.sha256).hexdigest()


def _prepared_sources(tmp_path: Path) -> tuple[Path, str, Path, str, Path, Path]:
    source = Path(__file__).resolve().parents[2]
    reviewed = tmp_path / "reviewed"
    reviewed.mkdir()
    shutil.copytree(source / "cascade", reviewed / "cascade", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (reviewed / ".gitignore").write_text("__pycache__/\n*.py[cod]\n", encoding="utf-8")
    _git(reviewed, "init", "-b", "reviewed")
    _git(reviewed, "config", "user.email", "runtime@example.test")
    _git(reviewed, "config", "user.name", "Runtime Test")
    _git(reviewed, "add", "cascade", ".gitignore")
    _git(reviewed, "commit", "-m", "accepted review")
    reviewed_revision = _git(reviewed, "rev-parse", "HEAD^{commit}")

    integrated = tmp_path / "integrated"
    _git(tmp_path, "clone", str(reviewed), str(integrated))
    _git(integrated, "config", "user.email", "runtime@example.test")
    _git(integrated, "config", "user.name", "Runtime Test")
    (integrated / "integrated.txt").write_text("guarded target\n", encoding="utf-8")
    _git(integrated, "add", "integrated.txt")
    _git(integrated, "commit", "-m", "integrate accepted review")
    integrated_revision = _git(integrated, "rev-parse", "HEAD^{commit}")

    key = b"runtime-install-authority-key-32-bytes-minimum"
    key_path = tmp_path / "authority.key"
    key_path.write_bytes(key)
    receipt_path = tmp_path / "deployment-receipt.json"
    unsigned: dict[str, object] = {
        "version": 1,
        "accepted_review_url": "https://forge.example/reviews/48",
        "authorized_actor": "release-operator@example.test",
        "environment": "isolated-runtime-test",
        "reviewed_repository": str(reviewed.resolve()),
        "reviewed_revision": reviewed_revision,
        "integrated_repository": str(integrated.resolve()),
        "integrated_revision": integrated_revision,
        "installed_source_sha256": source_fingerprint(reviewed / "cascade"),
    }
    receipt_id = _digest(unsigned)
    signed = {**unsigned, "receipt_id": receipt_id}
    signed["signature"] = _sign(signed, key)
    receipt_path.write_text(json.dumps(signed, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return reviewed, reviewed_revision, integrated, integrated_revision, key_path, receipt_path


def _bootstrap(
    reviewed: Path, integrated: Path, key: Path, receipt: Path, manifest: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable, "-m", "cascade.cli", "runtime-bootstrap",
            "--reviewed-source", str(reviewed),
            "--integrated-source", str(integrated),
            "--deployment-receipt", str(receipt),
            "--authority-key", str(key),
            "--output", str(manifest),
        ],
        cwd=reviewed,
        env={**os.environ, "PYTHONPATH": str(reviewed)},
        capture_output=True,
        text=True,
    )


def _rewrite_signed_receipt(
    receipt: Path, key: Path, **updates: object
) -> None:
    value = json.loads(receipt.read_text(encoding="utf-8"))
    value.update(updates)
    value.pop("signature", None)
    value.pop("receipt_id", None)
    receipt_id = _digest(value)
    value["receipt_id"] = receipt_id
    value["signature"] = _sign(value, key.read_bytes())
    receipt.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_bootstrap_requires_signed_clean_integrated_install_evidence(tmp_path: Path) -> None:
    reviewed, _, integrated, _, key, receipt = _prepared_sources(tmp_path)
    manifest = tmp_path / "runtime-authority.json"

    dirty_file = reviewed / "cascade" / "__init__.py"
    dirty_file.write_text(dirty_file.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    dirty = _bootstrap(reviewed, integrated, key, receipt, manifest)
    assert dirty.returncode == 1
    assert "dirty" in dirty.stderr
    _git(reviewed, "restore", "cascade/__init__.py")

    tampered = json.loads(receipt.read_text(encoding="utf-8"))
    tampered["authorized_actor"] = "unknown"
    receipt.write_text(json.dumps(tampered), encoding="utf-8")
    invalid = _bootstrap(reviewed, integrated, key, receipt, manifest)
    assert invalid.returncode == 1
    assert "digest" in invalid.stderr or "signature" in invalid.stderr
    assert not manifest.exists()


def test_bootstrap_rejects_stale_wrong_root_and_missing_authority(tmp_path: Path) -> None:
    reviewed, _, integrated, _, key, receipt = _prepared_sources(tmp_path)
    manifest = tmp_path / "runtime-authority.json"
    wrong_root = _bootstrap(reviewed, reviewed, key, receipt, manifest)
    assert wrong_root.returncode == 1
    assert "different integrated repository" in wrong_root.stderr

    (integrated / "later.txt").write_text("later\n", encoding="utf-8")
    _git(integrated, "add", "later.txt")
    _git(integrated, "commit", "-m", "target moved")
    stale = _bootstrap(reviewed, integrated, key, receipt, manifest)
    assert stale.returncode == 1
    assert "stale" in stale.stderr

    missing = _bootstrap(reviewed, integrated, tmp_path / "missing.key", receipt, manifest)
    assert missing.returncode == 1
    assert "installation authority" in missing.stderr


def test_bootstrap_rejects_review_unknown_to_guarded_target(tmp_path: Path) -> None:
    reviewed, _, _, _, key, receipt = _prepared_sources(tmp_path)
    unrelated = tmp_path / "unrelated-target"
    unrelated.mkdir()
    shutil.copytree(reviewed / "cascade", unrelated / "cascade")
    (unrelated / ".gitignore").write_text("__pycache__/\n*.py[cod]\n", encoding="utf-8")
    _git(unrelated, "init", "-b", "main")
    _git(unrelated, "config", "user.email", "runtime@example.test")
    _git(unrelated, "config", "user.name", "Runtime Test")
    _git(unrelated, "add", ".")
    _git(unrelated, "commit", "-m", "unrelated target")
    unrelated_revision = _git(unrelated, "rev-parse", "HEAD^{commit}")
    _rewrite_signed_receipt(
        receipt,
        key,
        integrated_repository=str(unrelated.resolve()),
        integrated_revision=unrelated_revision,
    )
    result = _bootstrap(reviewed, unrelated, key, receipt, tmp_path / "authority.json")
    assert result.returncode == 1
    assert "accepted review revision is unknown" in result.stderr


def test_real_worker_reports_host_verified_import_closure_and_restart(tmp_path: Path) -> None:
    reviewed, reviewed_revision, integrated, integrated_revision, key, receipt = _prepared_sources(tmp_path)
    manifest = tmp_path / "runtime-authority.json"
    bootstrap = _bootstrap(reviewed, integrated, key, receipt, manifest)
    assert bootstrap.returncode == 0, bootstrap.stderr
    authority = json.loads(manifest.read_text(encoding="utf-8"))

    product_fixture = tmp_path / "product"
    product_fixture.mkdir()
    product = prepare_drain_test_repo(product_fixture)
    port = free_port()
    stderr_path = tmp_path / "runtime-worker.stderr"
    env = {**os.environ, "PYTHONPATH": str(reviewed), "CASCADE_ENABLE_FAKE_PROVIDER": "1"}
    with stderr_path.open("w", encoding="utf-8") as stderr:
        launcher = subprocess.Popen(
            [
                sys.executable, "-m", "cascade.cli", "up", "--root", str(product),
                "--host", "127.0.0.1", "--port", str(port),
                "--runtime-authority", str(manifest), "--runtime-authority-key", str(key),
            ],
            cwd=reviewed,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=stderr,
            text=True,
        )
        try:
            base = f"http://127.0.0.1:{port}"
            wait_for_http(f"{base}/api/health")

            def _identity() -> dict:
                status, health = get_supervisor_health(base)
                return health["runtime_identity"] if status == 200 and health and health.get("runtime_identity") else {}

            poll_until(lambda: bool(_identity().get("verified")))
            first = _identity()
            first_pid = worker_pid_for_launcher(launcher.pid)
            assert first_pid is not None
            assert first["worker_pid"] == first_pid
            assert first["reviewed_revision"] == reviewed_revision
            assert first["integrated_revision"] == integrated_revision
            assert first["authority_manifest_id"] == authority["manifest_id"]
            assert first["deployment_receipt_id"] == authority["deployment_receipt_id"]
            assert first["accepted_review_url"] == "https://forge.example/reviews/48"
            assert first["authorized_actor"] == "release-operator@example.test"
            assert first["environment"] == "isolated-runtime-test"
            assert first["host_process_start_id"] == first["process_start_id"]
            assert first["host_boot_id"] in first["process_start_id"]
            assert len(first["loaded_modules"]) == 6
            assert all(Path(row["origin"]).is_relative_to(reviewed / "cascade") for row in first["loaded_modules"].values())

            os.kill(first_pid, signal.SIGKILL)
            poll_until(lambda: bool(_identity().get("verified")) and _identity().get("worker_pid") != first_pid, timeout=60)
            restarted = _identity()
            assert restarted["process_start_id"] != first["process_start_id"]
            assert restarted["capability_generation"] == first["capability_generation"]
        finally:
            launcher.send_signal(signal.SIGTERM)
            launcher.wait(timeout=60)
    assert launcher.returncode == 0, stderr_path.read_text(encoding="utf-8")


def test_worker_without_authority_is_host_observed_but_not_deployment_proof(tmp_path: Path) -> None:
    from tests.harness.cascade_up_subprocess import start_cascade_up

    proc = start_cascade_up(tmp_path)
    try:
        observed: tuple[int, dict | None] | None = None

        def _ready() -> bool:
            nonlocal observed
            observed = get_supervisor_health(proc.base)
            return bool(observed[1] and observed[1].get("runtime_identity"))

        poll_until(_ready)
        assert observed is not None
        status, health = observed
        assert status == 200 and health is not None
        identity = health["runtime_identity"]
        assert identity["verified"] is False
        assert identity["reason"] == "runtime_authority_missing"
        assert identity["host_process_start_id"] == identity["process_start_id"]
        assert len(identity["loaded_modules"]) == 6
    finally:
        proc.stop()


def test_host_verifier_rejects_stale_process_and_mixed_module_evidence(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[2]
    code = (
        "import json,time; from pathlib import Path; "
        "from cascade.workspace.runtime_identity import loaded_runtime_identity; "
        "from cascade.watchdog.capabilities import default_capability_registry; "
        "from cascade.workspace.supervisor_status import utc_now_iso; "
        f"x=loaded_runtime_identity(None,workspace_root=Path({str(tmp_path)!r}),"
        "capability_generation=default_capability_registry().fingerprint(),"
        "started_at=utc_now_iso()); print(json.dumps(x),flush=True); time.sleep(30)"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", code],
        env={**os.environ, "PYTHONPATH": str(source)},
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert proc.stdout is not None
        raw = json.loads(proc.stdout.readline())
        generation = default_capability_registry().fingerprint()
        checked = validate_loaded_runtime_identity(
            raw,
            authority=None,
            worker_pid=proc.pid,
            expected_workspace_root=tmp_path,
            expected_capability_generation=generation,
            observed_at=utc_now_iso(),
        )
        assert checked["host_process_start_id"] == raw["process_start_id"]

        stale = json.loads(json.dumps(raw))
        stale["process_start_id"] += "-stale"
        with pytest.raises(WorkspaceError, match="process-start"):
            validate_loaded_runtime_identity(
                stale, authority=None, worker_pid=proc.pid,
                expected_workspace_root=tmp_path,
                expected_capability_generation=generation, observed_at=utc_now_iso(),
            )

        mixed = json.loads(json.dumps(raw))
        first = next(iter(mixed["loaded_modules"].values()))
        first["origin"] = str(tmp_path / "foreign.py")
        with pytest.raises(WorkspaceError, match="wrong root"):
            validate_loaded_runtime_identity(
                mixed, authority=None, worker_pid=proc.pid,
                expected_workspace_root=tmp_path,
                expected_capability_generation=generation, observed_at=utc_now_iso(),
            )

        refused = verify_loaded_runtime_identity(
            raw, authority=None, worker_pid=proc.pid,
            expected_workspace_root=tmp_path,
            expected_capability_generation="0" * 64, observed_at=utc_now_iso(),
        )
        assert refused["state"] == "refused"
        assert "capability generation" in str(refused["reason"])
        pending = verify_loaded_runtime_identity(
            raw, authority=None, worker_pid=proc.pid,
            expected_workspace_root=tmp_path,
            expected_capability_generation=generation, observed_at=utc_now_iso(),
        )
        assert pending["state"] == "pending"
        assert "trust key" in str(pending["reason"])
    finally:
        proc.terminate()
        proc.wait(timeout=10)
