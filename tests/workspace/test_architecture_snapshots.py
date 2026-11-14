"""Durable revision-pinned architecture browsing snapshots."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import cascade.workspace.architecture_browsing as browsing
from cascade.workspace import (
    ArchitectureSnapshotStore,
    C4ArtifactRenderer,
    C4RenderArtifact,
    C4RenderFailure,
    C4RenderScheduler,
    ProjectContext,
    resolve_design_ownership,
)
from tests.support import make_repo

_VERSIONED_WORKSPACE = (
    Path(__file__).parents[2]
    / "architecture"
    / "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
)


class _Result:
    def __init__(self, value: C4RenderArtifact) -> None:
        self.value = value

    def wait(self, timeout: float | None = None) -> C4RenderArtifact:
        return self.value


class _Renderer(C4ArtifactRenderer):
    def __init__(self, cache: Path, *, fail: bool = False) -> None:
        super().__init__(cache)
        self.calls = 0
        self.fail = fail

    def submit(self, closure, settings=None):
        self.calls += 1
        if self.fail:
            return _Result(C4RenderArtifact(
                status="render_error",
                closure_digest=closure.digest,
                failure=C4RenderFailure("export_failed", "svg_export", "fixture failure"),
            ))
        return _Result(C4RenderArtifact(
            status="ready",
            closure_digest=closure.digest,
            cache_key="fixture-cache",
            semantic_workspace_sha256="a" * 64,
            view_keys=("cascade-context", "cascade-containers"),
            revision=closure.revision,
        ))


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _commit(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=root, check=True)
    return _git(root, "rev-parse", "HEAD")


def _project(tmp_path: Path) -> tuple[Path, ProjectContext, str]:
    root = make_repo(tmp_path)
    project = ProjectContext.colocated(root)
    resolve_design_ownership(project, ".")
    shutil.copytree(_VERSIONED_WORKSPACE, project.editable_architecture_root)
    revision = _commit(root, "architecture model")
    return root, project, revision


def _wait_ready(store: ArchitectureSnapshotStore, snapshot_id: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        snapshot = store.get(snapshot_id)
        if snapshot.state != "pending":
            return snapshot
        time.sleep(0.02)
    raise AssertionError("snapshot render did not finish")


def test_snapshot_pins_committed_bytes_and_reuses_render_after_restart(tmp_path: Path) -> None:
    root, project, revision = _project(tmp_path)
    renderer = _Renderer(tmp_path / "cache")
    scheduler = C4RenderScheduler(root, renderer=renderer)
    store = ArchitectureSnapshotStore(project, root, scheduler=scheduler)
    try:
        # Dirty model bytes must not enter the pinned closure.
        project.editable_architecture_root.joinpath("views.dsl").write_text(
            "dirty and invalid\n", encoding="utf-8"
        )
        first = store.create()
        ready = _wait_ready(store, first.snapshot_id)
        duplicate = store.create()

        assert ready.state == "ready"
        assert ready.descriptor["revisions"] == {
            "code": revision,
            "documentation": revision,
        }
        assert ready.descriptor["mapping"]["revision"] == revision
        assert ready.descriptor["association"]["provenance"] == "colocated"
        assert ready.descriptor["source_closure"]["revision"] == revision
        assert len(ready.descriptor["render"]["identity"]) == 64
        assert duplicate.snapshot_id == first.snapshot_id
        assert renderer.calls == 1
        assert store.view_state(first.snapshot_id, "unknown") == {
            "state": "missing_view", "view_key": "unknown"
        }
    finally:
        scheduler.close()

    restarted_scheduler = C4RenderScheduler(
        root, renderer=renderer, start_worker=False
    )
    restarted = ArchitectureSnapshotStore(
        project, root, scheduler=restarted_scheduler
    )
    try:
        recovered = restarted.get(first.snapshot_id)
        assert recovered.state == "ready"
        assert recovered.descriptor == ready.descriptor
        assert renderer.calls == 1
    finally:
        restarted_scheduler.close()


def test_head_advance_keeps_old_snapshot_until_explicit_whole_refresh(tmp_path: Path) -> None:
    root, project, first_revision = _project(tmp_path)
    renderer = _Renderer(tmp_path / "cache")
    scheduler = C4RenderScheduler(root, renderer=renderer)
    store = ArchitectureSnapshotStore(project, root, scheduler=scheduler)
    try:
        first = store.create()
        _wait_ready(store, first.snapshot_id)
        root.joinpath("code.py").write_text("new revision\n", encoding="utf-8")
        second_revision = _commit(root, "advance branch")

        assert store.get(first.snapshot_id).descriptor["revisions"]["code"] == first_revision
        status = store.head_status(first.snapshot_id)
        assert status["changed"] is True
        assert status["current_revision"] == second_revision

        refreshed = store.refresh(first.snapshot_id)
        refreshed = _wait_ready(store, refreshed.snapshot_id)
        assert refreshed.snapshot_id != first.snapshot_id
        assert refreshed.descriptor["revisions"] == {
            "code": second_revision,
            "documentation": second_revision,
        }
        assert store.head_status(refreshed.snapshot_id)["changed"] is False
    finally:
        scheduler.close()


def test_missing_model_and_render_failure_are_explicit_and_durable(tmp_path: Path) -> None:
    missing_root = make_repo(tmp_path / "missing")
    missing_project = ProjectContext.colocated(missing_root)
    resolve_design_ownership(missing_project, ".")
    _commit(missing_root, "mapping only")
    missing_scheduler = C4RenderScheduler(missing_root, start_worker=False)
    missing_store = ArchitectureSnapshotStore(
        missing_project, missing_root, scheduler=missing_scheduler
    )
    try:
        missing = missing_store.create()
        assert missing.state == "missing_model"
        assert missing.reason_code == "missing_model"
        assert missing_store.get(missing.snapshot_id).state == "missing_model"
    finally:
        missing_scheduler.close()

    root, project, _ = _project(tmp_path / "failure")
    renderer = _Renderer(tmp_path / "failure-cache", fail=True)
    scheduler = C4RenderScheduler(root, renderer=renderer)
    store = ArchitectureSnapshotStore(project, root, scheduler=scheduler)
    try:
        failed = store.create()
        failed = _wait_ready(store, failed.snapshot_id)
        assert failed.state == "render_failed"
        assert failed.reason_code == "export_failed"
        assert failed.message == "fixture failure"
    finally:
        scheduler.close()


def test_split_snapshot_pins_exact_documentation_association(
    tmp_path: Path, monkeypatch,
) -> None:
    target = make_repo(tmp_path / "target")
    tracking = make_repo(tmp_path / "tracking")
    project = ProjectContext.split(
        target, tracking, architecture_destination="tracking"
    )
    resolve_design_ownership(project, ".")
    code_revision = _commit(target, "mapping")
    shutil.copytree(_VERSIONED_WORKSPACE, project.editable_architecture_root)
    documentation_revision = _commit(tracking, "architecture model")
    monkeypatch.setattr(
        browsing,
        "_recorded_candidates",
        lambda _project: (
            browsing._Candidate(
                code_revision,
                documentation_revision,
                "promotion",
                "promotion-exact",
            ),
        ),
    )
    renderer = _Renderer(tmp_path / "split-cache")
    scheduler = C4RenderScheduler(target, renderer=renderer)
    store = ArchitectureSnapshotStore(project, target, scheduler=scheduler)
    try:
        snapshot = store.create()
        snapshot = _wait_ready(store, snapshot.snapshot_id)
        assert snapshot.state == "ready"
        assert snapshot.descriptor["revisions"] == {
            "code": code_revision,
            "documentation": documentation_revision,
        }
        assert snapshot.descriptor["architecture_destination"] == "tracking"
        assert snapshot.descriptor["association"] == {
            "provenance": "promotion",
            "evidence_id": "promotion-exact",
        }
        assert snapshot.descriptor["source_closure"]["revision"] == documentation_revision
    finally:
        scheduler.close()


def test_oversized_pinned_source_is_rejected_before_render(tmp_path: Path) -> None:
    root, project, _ = _project(tmp_path)
    project.editable_architecture_root.joinpath("model.dsl").write_text(
        "x" * (4 * 1024 * 1024), encoding="utf-8"
    )
    _commit(root, "oversized model")
    renderer = _Renderer(tmp_path / "oversized-cache")
    scheduler = C4RenderScheduler(root, renderer=renderer, start_worker=False)
    store = ArchitectureSnapshotStore(project, root, scheduler=scheduler)
    try:
        snapshot = store.create()
        assert snapshot.state == "oversized_artifact"
        assert snapshot.reason_code == "oversized_artifact"
        assert renderer.calls == 0
    finally:
        scheduler.close()
