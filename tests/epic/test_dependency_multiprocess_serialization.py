"""Cross-process manifest/approval serialization at the authority boundary."""

from __future__ import annotations

import multiprocessing
from dataclasses import replace
from pathlib import Path

from cascade.epic.dependency_approvals import (
    AuthenticatedHuman,
    approve_dependency_installations,
    read_installation_approvals,
)
from cascade.epic.dependency_lock import dependency_state_lock
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestDraft,
    EnvironmentIdentity,
    InstallationBinding,
    write_dependency_manifest,
)
from tests.support import add_doc, make_repo


def _approval_process(
    root: str,
    binding_payload: dict[str, str | dict[str, str]],
    ready,
    result,
) -> None:
    ready.put(True)
    binding = InstallationBinding.from_dict(binding_payload)
    try:
        approve_dependency_installations(
            "epic_001",
            (binding.dependency_id,),
            approver=AuthenticatedHuman("race@example.test"),
            root=Path(root),
            expected_manifest_revision=1,
            expected_bindings={binding.dependency_id: binding},
        )
    except Exception as exc:  # result is asserted by the parent process
        result.put((type(exc).__name__, str(exc)))
    else:
        result.put(("approved", ""))


def _entry(target: EnvironmentIdentity) -> DependencyEntry:
    return DependencyEntry(
        dependency_id="dep_tool",
        version="1.2.3",
        source="https://tool.example/tool.tgz",
        digest="sha256:tool",
        target_environment=target,
        install_scope="project-local",
        install_destination=".tools/tool",
        operation="install tool 1.2.3",
        cleanup_plan="remove .tools/tool",
        verification_recipe=".tools/tool --version",
    )


def test_manifest_change_cannot_race_reviewed_approval(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    target = EnvironmentIdentity("ci", "host", "linux", "x86_64")
    entry = _entry(target)
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(target, None, False, (entry,)),
        root=root,
        expected_revision=0,
    )

    context = multiprocessing.get_context("spawn")
    ready = context.Queue()
    result = context.Queue()
    reviewed = InstallationBinding.from_entry(entry)
    with dependency_state_lock(root=root):
        process = context.Process(
            target=_approval_process,
            args=(str(root), reviewed.to_dict(), ready, result),
        )
        process.start()
        assert ready.get(timeout=10) is True
        changed = replace(entry, operation="install tool 1.2.3 with changed flags")
        write_dependency_manifest(
            "epic_001",
            DependencyManifestDraft(target, None, False, (changed,)),
            root=root,
            expected_revision=1,
        )

    outcome, detail = result.get(timeout=10)
    process.join(timeout=10)
    assert process.exitcode == 0
    assert outcome == "DependencyApprovalError"
    assert "stale manifest revision" in detail
    assert read_installation_approvals("epic_001", root=root) == ()
