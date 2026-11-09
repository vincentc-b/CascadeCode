"""Bounded offline rendering of a confined C4 source closure."""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import time
from pathlib import Path

from cascade.workspace import (
    C4ArtifactRenderer,
    C4RenderArtifact,
    C4RenderSettings,
    C4SourceClosure,
    C4SourceFile,
    STRUCTURIZR_IMAGE,
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
    result = renderer.submit(closure).wait(timeout=120)

    assert result.status == "ready", result
    assert result.cache_hit is False
    assert result.view_keys == ("cascade-containers", "cascade-landscape")
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
    shutil.copytree(_VERSIONED_WORKSPACE, root)
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
            owner="feat_034_002",
            revision=revision,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in sorted(root.iterdir())
        if path.is_file()
    )
    digest = hashlib.sha256(
        "".join(f"{item.path}:{item.sha256}" for item in files).encode()
    ).hexdigest()
    return C4SourceClosure(
        target_repository_key=_VERSIONED_WORKSPACE.name,
        destination_repository_key=_VERSIONED_WORKSPACE.name,
        destination_repository_role="target",
        code_directory=Path("."),
        design_owner_directory=Path("."),
        revision=revision,
        architecture_root=Path("architecture") / _VERSIONED_WORKSPACE.name,
        source=Path("workspace.dsl"),
        files=files,
        digest=digest,
        input_directory=root,
        contract=contract,
    )


def revision_fragment(reference: str) -> bool:
    return reference.startswith("revision:") and ";paths:architecture/" in reference
