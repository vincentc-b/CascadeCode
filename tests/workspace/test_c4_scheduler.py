"""Durable, bounded C4 scheduling and interruption recovery."""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.workspace import (
    C4ArtifactRenderer,
    C4RenderAdmissionError,
    C4RenderArtifact,
    C4RenderFailure,
    C4RenderScheduler,
    C4SourceClosure,
    C4SourceFile,
    validate_c4_workspace,
)


class _ResultOperation:
    def __init__(self, result: C4RenderArtifact) -> None:
        self.result = result

    def wait(self, timeout: float | None = None) -> C4RenderArtifact:
        return self.result


class _RecordingRenderer(C4ArtifactRenderer):
    def __init__(self, cache_directory: Path, *, fail: bool = False) -> None:
        super().__init__(cache_directory)
        self.calls = 0
        self.fail = fail

    def submit(self, closure, settings=None):
        self.calls += 1
        if self.fail:
            result = C4RenderArtifact(
                status="render_error",
                closure_digest=closure.digest,
                failure=C4RenderFailure("export_failed", "svg_export", "fixture failure"),
            )
        else:
            result = C4RenderArtifact(
                status="ready", closure_digest=closure.digest,
                cache_key="cache-key", semantic_workspace_sha256="a" * 64,
                view_keys=("context",), revision=closure.revision,
            )
        return _ResultOperation(result)


def test_scheduler_deduplicates_exact_identity_and_persists_verified_result(tmp_path: Path) -> None:
    root = _git_root(tmp_path)
    renderer = _RecordingRenderer(tmp_path / "cache")
    scheduler = C4RenderScheduler(root, renderer=renderer)
    try:
        closure = _closure(tmp_path, "one")
        first = scheduler.admit(closure, owner="feature", snapshot_id="a")
        duplicate = scheduler.admit(closure, owner="branch", snapshot_id="b")
        result = first.wait(2)
        assert duplicate.operation_id == first.operation_id
        assert result.status == "ready"
        assert result.attempts == 1
        assert result.artifact and result.artifact.cache_key == "cache-key"
        assert renderer.calls == 1

        restarted = C4RenderScheduler(root, renderer=renderer, start_worker=False)
        try:
            durable = restarted.get(first.operation_id)
            assert durable.status == "ready"
            assert durable.artifact and durable.artifact.semantic_workspace_sha256 == "a" * 64
        finally:
            restarted.close()
    finally:
        scheduler.close()


def test_scheduler_bounds_active_plus_pending_and_retry_keeps_identity(tmp_path: Path) -> None:
    root = _git_root(tmp_path)
    scheduler = C4RenderScheduler(
        root, renderer=_RecordingRenderer(tmp_path / "cache", fail=True),
        max_active=1, max_pending=1, start_worker=False,
    )
    try:
        one = scheduler.admit(_closure(tmp_path, "one"), owner="feature", snapshot_id="one")
        scheduler.admit(_closure(tmp_path, "two"), owner="feature", snapshot_id="two")
        with pytest.raises(C4RenderAdmissionError) as raised:
            scheduler.admit(_closure(tmp_path, "three"), owner="feature", snapshot_id="three")
        assert raised.value.code == "queue_full"
        assert raised.value.retry_after_seconds == 2
        assert one.snapshot().status == "pending"  # Reads do not start a renderer.
    finally:
        scheduler.close()

    failing = C4RenderScheduler(root, renderer=_RecordingRenderer(tmp_path / "cache", fail=True))
    try:
        failed = one.wait(2)
        assert failed.status == "failed"
        retried = failing.retry(one.operation_id)
        assert retried.operation_id == one.operation_id
        assert retried.wait(2).attempts == 2
    finally:
        failing.close()


def test_startup_reclaims_interruption_once_then_requires_explicit_retry(tmp_path: Path) -> None:
    root = _git_root(tmp_path)
    scheduler = C4RenderScheduler(root, start_worker=False)
    operation = scheduler.admit(_closure(tmp_path, "one"), owner="feature", snapshot_id="one")
    ledger_path = root / ".cascade" / "c4-render-operations.json"
    ledger = json.loads(ledger_path.read_text())
    row = ledger["operations"][operation.operation_id]
    row.update(
        status="running", attempts=1,
        lease={"worker_id": "dead", "pid": 99999999, "expires_at": time.time() - 1},
    )
    ledger_path.write_text(json.dumps(ledger))

    recovered = C4RenderScheduler(root, start_worker=False)
    try:
        assert recovered.get(operation.operation_id).status == "pending"
        assert recovered.get(operation.operation_id).recovery_attempts == 1
    finally:
        recovered.close()

    ledger = json.loads(ledger_path.read_text())
    row = ledger["operations"][operation.operation_id]
    row.update(
        status="running", attempts=2,
        lease={"worker_id": "dead-again", "pid": 99999999, "expires_at": time.time() - 1},
    )
    ledger_path.write_text(json.dumps(ledger))
    exhausted = C4RenderScheduler(root, start_worker=False)
    try:
        result = exhausted.get(operation.operation_id)
        assert result.status == "failed"
        assert result.failure and "automatic recovery attempt" in result.failure.message
    finally:
        exhausted.close()


def test_restarted_worker_fences_stale_finish_from_crashed_attempt(tmp_path: Path) -> None:
    """A late pre-restart result cannot overwrite the recovered attempt."""

    root = _git_root(tmp_path)
    old = C4RenderScheduler(root, start_worker=False)
    operation = old.admit(
        _closure(tmp_path, "race"), owner="feature", snapshot_id="race"
    )
    claimed = old._claim()
    assert claimed is not None

    ledger_path = root / ".cascade" / "c4-render-operations.json"
    ledger = json.loads(ledger_path.read_text())
    row = ledger["operations"][operation.operation_id]
    row["lease"] = {
        "worker_id": "crashed-worker",
        "pid": 99999999,
        "expires_at": time.time() - 1,
    }
    ledger_path.write_text(json.dumps(ledger))

    restarted = C4RenderScheduler(root, start_worker=False)
    try:
        recovered = restarted._claim()
        assert recovered is not None
        assert recovered["attempts"] == 2

        old._finish(
            operation.operation_id,
            C4RenderArtifact(
                status="render_error",
                closure_digest=claimed["closure"]["digest"],
                failure=C4RenderFailure(
                    "internal_error", "scheduler", "late crashed-attempt result"
                ),
            ),
        )
        assert restarted.get(operation.operation_id).status == "running"

        restarted._finish(
            operation.operation_id,
            C4RenderArtifact(
                status="ready",
                closure_digest=recovered["closure"]["digest"],
                cache_key="recovered-cache",
                semantic_workspace_sha256="a" * 64,
                view_keys=("context",),
                revision="1" * 40,
            ),
        )
        final = restarted.get(operation.operation_id)
        assert final.status == "ready"
        assert final.attempts == 2
        assert final.recovery_attempts == 1
        assert final.failure is None
    finally:
        old.close()
        restarted.close()


def _git_root(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True, capture_output=True)
    return root


def _closure(tmp_path: Path, name: str) -> C4SourceClosure:
    root = tmp_path / f"input-{name}"
    root.mkdir()
    (root / "workspace.contract.json").write_text(
        json.dumps({
            "version": 1,
            "workspace": {"source": "workspace.dsl", "owner": "feature"},
            "fragments": [],
            "elements": [],
            "relationships": [],
            "views": [],
            "renames": [],
        }) + "\n"
    )
    (root / "workspace.dsl").write_text(
        f"workspace \"{name}\" {{}}\n!impliedRelationships false\n"
    )
    revision = "1" * 40
    files = tuple(
        C4SourceFile(
            path=path.relative_to(root), repository_path=path.relative_to(root),
            owner="feature", revision=revision,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.iterdir())
    )
    closure = C4SourceClosure(
        target_repository_key="project", destination_repository_key="project",
        destination_repository_role="target", code_directory=Path("."),
        design_owner_directory=Path("."), revision=revision,
        architecture_root=Path("architecture/project"), source=Path("workspace.dsl"),
        files=files, digest="", input_directory=root,
        contract=validate_c4_workspace(root),
    )
    return replace(closure, digest=closure.computed_digest())


def test_completed_render_keeps_pinned_identity_after_adapter_upgrade(tmp_path: Path, monkeypatch) -> None:
    import cascade.workspace.c4_scheduler as module
    root = _git_root(tmp_path)
    renderer = _RecordingRenderer(tmp_path / "cache")
    scheduler = C4RenderScheduler(root, renderer=renderer)
    try:
        closure = _closure(tmp_path, "pinned")
        op = scheduler.admit(closure, owner="feature", snapshot_id="snapshot")
        assert op.wait(2).status == "ready"
        replacement = tmp_path / "new-adapter.java"
        replacement.write_text("different adapter bytes")
        monkeypatch.setattr(module, "_BINDING_ADAPTER", replacement)
        monkeypatch.setattr(module, "_ARTIFACT_VERSION", 99)
        artifact = scheduler.get_semantic_artifact(op.operation_id, artifact_ref="snapshot")
        assert artifact.render.closure_digest == closure.digest
        assert renderer.calls == 1
        ledger = scheduler._read()
        ledger["operations"][op.operation_id]["identity_inputs"]["adapter_sha256"] = "f" * 64
        scheduler._write(ledger)
        with pytest.raises(ValueError, match="identity"):
            scheduler.get_semantic_artifact(op.operation_id, artifact_ref="snapshot")
    finally:
        scheduler.close()


def test_legacy_completed_render_requires_original_provenance(tmp_path: Path) -> None:
    import cascade.workspace.c4_scheduler as module
    root = _git_root(tmp_path)
    scheduler = C4RenderScheduler(root, renderer=_RecordingRenderer(tmp_path / "cache"))
    try:
        closure = _closure(tmp_path, "legacy")
        op = scheduler.admit(closure, owner="feature", snapshot_id="snapshot")
        assert op.wait(2).status == "ready"
        ledger = scheduler._read()
        row = ledger["operations"].pop(op.operation_id)
        inputs = row.pop("identity_inputs")
        inputs.update(artifact_version=3,
            adapter_sha256="04a32a0141a2578724d6826b74d2192ba9bb94f971b00600350d1225d5ac3a2b")
        identity = module._identity_digest(inputs)
        operation_id = "c4-render-" + identity
        row.update(operation_id=operation_id, render_identity=identity)
        directory = tmp_path / "legacy-output"
        directory.mkdir()
        manifest = {
            "version": 3, "closure_digest": closure.digest,
            "image_digest": inputs["image_digest"], "settings": inputs["settings"],
            "source_provenance": module._source_provenance(closure),
        }
        manifest_path = directory / "manifest.json"
        manifest_path.write_text(json.dumps(manifest))
        row["artifact"]["artifact_directory"] = str(directory)
        ledger["operations"][operation_id] = row
        scheduler._write(ledger)
        assert scheduler.get_semantic_artifact(operation_id, artifact_ref="snapshot")
        manifest["closure_digest"] = "f" * 64
        manifest_path.write_text(json.dumps(manifest))
        with pytest.raises(ValueError, match="provenance"):
            scheduler.get_semantic_artifact(operation_id, artifact_ref="snapshot")
    finally:
        scheduler.close()


def test_pending_render_does_not_publish_new_adapter_under_old_identity(tmp_path: Path, monkeypatch) -> None:
    import cascade.workspace.c4_scheduler as module
    root = _git_root(tmp_path)
    queued = C4RenderScheduler(root, start_worker=False)
    closure = _closure(tmp_path, "queued")
    operation = queued.admit(closure, owner="branch", snapshot_id="old")
    queued.close()
    replacement = tmp_path / "new-adapter.java"
    replacement.write_text("new renderer")
    monkeypatch.setattr(module, "_BINDING_ADAPTER", replacement)
    renderer = _RecordingRenderer(tmp_path / "cache")
    current = C4RenderScheduler(root, renderer=renderer)
    try:
        result = operation.wait(2)
        assert result.status == "failed"
        assert "refresh the architecture snapshot" in result.failure.message
        assert renderer.calls == 0
        refreshed = current.admit(closure, owner="branch", snapshot_id="new")
        assert refreshed.operation_id != operation.operation_id
        assert refreshed.wait(2).status == "ready"
    finally:
        current.close()
