"""Bounded offline rendering of a confined C4 source closure."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.workspace import (
    C4ArtifactRenderer,
    C4RenderArtifact,
    C4RenderSettings,
    C4SemanticModelArtifact,
    C4SourceClosure,
    C4SourceFile,
    STRUCTURIZR_IMAGE,
    compute_c4_semantic_diff,
    validate_c4_workspace,
)


_REPOSITORY_ROOT = Path(__file__).parents[2]
_VERSIONED_WORKSPACE = (
    _REPOSITORY_ROOT
    / "architecture"
    / "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
)


def test_real_pinned_renderer_publishes_one_validated_handoff_and_cache(
    tmp_path: Path,
) -> None:
    closure = _closure(tmp_path)
    renderer = C4ArtifactRenderer(tmp_path / "cache")

    assert C4RenderArtifact.first().status == "first"
    settings = C4RenderSettings()
    result = renderer.submit(closure, settings).wait(
        timeout=settings.timeout_seconds + 5
    )

    assert result.status == "ready", result
    assert result.cache_hit is False
    assert result.view_keys == (
        "cascade-containers",
        "cascade-context",
        "cascade-landscape",
        "cascade-supervisor-components",
    )
    assert result.semantic_workspace and result.semantic_workspace.is_file()
    assert result.embedded_workspace and result.embedded_workspace.is_file()
    assert result.static_directory
    assert result.static_directory.joinpath("index.html").is_file()
    assert result.svg_files
    assert result.interactive is True
    assert result.binding_manifest and result.binding_manifest.is_file()
    assert result.source_diff_reference and revision_fragment(result.source_diff_reference)
    assert all("data-cascade-export-id" in path.read_text() for path in result.svg_files)
    assert result.artifact_directory and result.artifact_directory.joinpath(
        "manifest.json"
    ).is_file()

    cached = renderer.submit(closure).wait(timeout=5)
    assert cached.status == "ready"
    assert cached.cache_hit is True
    assert cached.artifact_directory == result.artifact_directory
    assert cached.binding_manifest == result.binding_manifest

    model = C4SemanticModelArtifact("render:self", cached, closure.contract)
    diff = compute_c4_semantic_diff(
        model, model, source_diff_reference="revision:self..self"
    )
    assert diff.state == "unchanged"
    assert diff.changed_view_keys == ()

    assert cached.semantic_workspace
    original_workspace = cached.semantic_workspace.read_bytes()
    cached.semantic_workspace.write_bytes(original_workspace + b"\n")
    corrupt = renderer.submit(closure).wait(timeout=5)
    assert corrupt.status == "render_error"
    assert corrupt.failure and corrupt.failure.code == "invalid_artifact"
    assert "artifact bytes" in corrupt.failure.message
    cached.semantic_workspace.write_bytes(original_workspace)

    assert cached.artifact_directory
    manifest_path = cached.artifact_directory / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_provenance"]["revision"] = "0" * 40
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    stale = renderer.submit(closure).wait(timeout=5)
    assert stale.status == "render_error"
    assert stale.failure and stale.failure.code == "invalid_artifact"
    assert "provenance" in stale.failure.message


@pytest.mark.parametrize("mutation", ["changed", "missing", "extra"])
def test_source_inventory_and_hash_drift_fail_before_runtime(
    tmp_path: Path, mutation: str
) -> None:
    closure = _closure(tmp_path)
    if mutation == "changed":
        (closure.input_directory / "workspace.dsl").write_text(
            "workspace changed {}", encoding="utf-8"
        )
    elif mutation == "missing":
        (closure.input_directory / closure.files[-1].path).unlink()
    else:
        (closure.input_directory / "unexpected.dsl").write_text(
            "workspace {}", encoding="utf-8"
        )

    result = C4ArtifactRenderer(
        tmp_path / "cache", runtime=str(tmp_path / "runtime-must-not-run")
    ).submit(closure).wait(timeout=5)

    assert result.status == "render_error"
    assert result.failure and result.failure.code == "invalid_artifact"
    assert result.failure.stage == "source"
    assert "provenance" in result.failure.message


def test_render_stages_use_verified_snapshot_after_source_mutation(
    tmp_path: Path,
) -> None:
    closure = _closure(tmp_path)
    original = (closure.input_directory / closure.source).read_bytes()

    class SnapshotProbeRenderer(C4ArtifactRenderer):
        snapshot_source: Path | None = None
        observed: bytes | None = None

        def _render_verified(
            self,
            verified: C4SourceClosure,
            settings: C4RenderSettings,
            cancelled: threading.Event,
        ) -> C4RenderArtifact:
            self.snapshot_source = verified.input_directory
            (closure.input_directory / closure.source).write_text(
                "workspace changed {}", encoding="utf-8"
            )
            self.observed = (verified.input_directory / verified.source).read_bytes()
            return C4RenderArtifact(status="empty", closure_digest=verified.digest)

    renderer = SnapshotProbeRenderer(tmp_path / "cache")
    result = renderer.submit(closure).wait(timeout=5)

    assert result.status == "empty"
    assert renderer.observed == original
    assert renderer.snapshot_source != closure.input_directory
    assert renderer.snapshot_source and not renderer.snapshot_source.exists()


def test_container_contract_is_immutable_offline_read_only_and_bounded(
    tmp_path: Path,
) -> None:
    closure = _closure(tmp_path)
    renderer = C4ArtifactRenderer(tmp_path / "cache")
    output = tmp_path / "output"
    output.mkdir()
    command = renderer._container_command(
        closure,
        output,
        C4RenderSettings(),
        ["validate", "-workspace", "/workspace/workspace.dsl"],
    )

    assert command[:2] == ["docker", "run"]
    for option in (
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=256",
        "--memory=1536m",
        "--cpus=2",
    ):
        assert option in command
    assert f"{closure.input_directory.resolve()}:/workspace:ro" in command
    assert f"{output.resolve()}:/output:rw" in command
    assert STRUCTURIZR_IMAGE in command
    user = command[command.index("--user") + 1]
    assert user.split(":", 1)[0] != "0"

    bindings = output / "raw-bindings" / "view.json"
    svg = output / "raw-bound-svg" / "view.svg"
    binding_command = renderer._binding_command(
        closure,
        output,
        C4RenderSettings(),
        view_key="cascade-landscape",
        bindings=bindings,
        svg=svg,
    )
    assert "--entrypoint" in binding_command
    assert "/bin/sh" in binding_command
    assert any(
        item.endswith(":/adapter/RendererBindingAdapter.java:ro")
        for item in binding_command
    )
    assert binding_command[-1] == "cascade-landscape"


def test_background_cancellation_and_runtime_failure_are_structured(
    tmp_path: Path,
) -> None:
    closure = _closure(tmp_path)
    slow_runtime = tmp_path / "slow-runtime"
    slow_runtime.write_text("#!/bin/sh\nsleep 30\n", encoding="utf-8")
    slow_runtime.chmod(0o755)
    renderer = C4ArtifactRenderer(tmp_path / "cancel-cache", runtime=str(slow_runtime))

    operation = renderer.submit(closure)
    time.sleep(0.1)
    assert operation.snapshot().status == "running"
    assert operation.cancel()
    assert operation.wait(timeout=5).status == "cancelled"

    missing = C4ArtifactRenderer(
        tmp_path / "error-cache", runtime=str(tmp_path / "missing-runtime")
    ).submit(closure).wait(timeout=5)
    assert missing.status == "render_error"
    assert missing.failure is not None
    assert missing.failure.code == "image_unavailable"
    assert missing.failure.stage == "image"


def _closure(tmp_path: Path) -> C4SourceClosure:
    root = tmp_path / "input"
    root.mkdir()
    # The real architecture directory also retains nested renderer evidence.
    # A source closure contains only the contract's declared, reachable inputs.
    for name in ("workspace.contract.json", "workspace.dsl", "model.dsl", "views.dsl"):
        shutil.copy2(_VERSIONED_WORKSPACE / name, root / name)
    contract = validate_c4_workspace(root)
    revision = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=_REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    files = tuple(
        C4SourceFile(
            path=path.relative_to(root),
            repository_path=path.relative_to(root),
            owner="task_034_007_002",
            revision=revision,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.iterdir())
        if path.is_file()
    )
    closure = C4SourceClosure(
        target_repository_key=_VERSIONED_WORKSPACE.name,
        destination_repository_key=_VERSIONED_WORKSPACE.name,
        destination_repository_role="target",
        code_directory=Path("."),
        design_owner_directory=Path("."),
        revision=revision,
        architecture_root=Path("architecture") / _VERSIONED_WORKSPACE.name,
        source=Path("workspace.dsl"),
        files=files,
        digest="",
        input_directory=root,
        contract=contract,
    )
    return replace(closure, digest=closure.computed_digest())


def revision_fragment(reference: str) -> bool:
    return reference.startswith("revision:") and ";paths:architecture/" in reference
