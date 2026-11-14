"""Shared public authoring contract for the first dependency declaration."""

from __future__ import annotations

from pathlib import Path

ENVIRONMENT_FIELDS = (
    "environment_id",
    "kind",
    "platform",
    "architecture",
    "runner",
    "repository",
    "worktree",
    "sandbox",
    "runtime",
    "container_digest",
)
DEPENDENCY_TEXT_FIELDS = (
    "dependency_id",
    "version",
    "source",
    "digest",
    "install_scope",
    "operation",
    "cleanup_plan",
    "verification_recipe",
    "requested_range",
    "resolved_version",
    "expected_verification_result",
    "install_destination",
    "integrity_reference",
)
DEPENDENCY_LIST_FIELDS = (
    "feasibility_proof_requirements",
    "feasibility_proof_references",
    "lock_references",
)


def manifest_schema() -> dict:
    text = {"type": "string", "minLength": 1}
    environment = {
        "type": "object",
        "properties": {k: dict(text) for k in ENVIRONMENT_FIELDS},
        "required": list(ENVIRONMENT_FIELDS),
        "additionalProperties": False,
    }
    properties = {k: dict(text) for k in DEPENDENCY_TEXT_FIELDS}
    properties.update(
        {k: {"type": "array", "items": dict(text)} for k in DEPENDENCY_LIST_FIELDS}
    )
    properties["target_environment"] = environment
    properties["dependency_id"]["pattern"] = "^dep_[a-z0-9][a-z0-9_-]*$"
    return {
        "type": "object",
        "description": "Declare exact prerequisites; an empty list requires an explicit none_required=true decision. This grants no installation authority.",
        "properties": {
            "target_environment": environment,
            "actual_environment": {"anyOf": [environment, {"type": "null"}]},
            "none_required": {"type": "boolean"},
            "dependencies": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            },
        },
        "required": [
            "target_environment",
            "actual_environment",
            "none_required",
            "dependencies",
        ],
        "additionalProperties": False,
    }


def authoring_context(epic_id: str, *, root: Path) -> dict:
    from cascade.board.context import get_project_context
    from cascade.epic.local_dependency_executor import local_environment_identity
    from cascade.epic.dependency_manifests import read_dependency_manifest
    from cascade.workspace.integration_worktree import locate_trunk

    manifest = read_dependency_manifest(epic_id, root=root)
    project = get_project_context()
    execution_root = project.target.root if project is not None else locate_trunk(root)
    observed = local_environment_identity(execution_root).to_dict()
    return {
        "state": "declared" if manifest else "declaration_required",
        "expected_revision": manifest.revision if manifest else 0,
        "observed_local_environment": observed,
        "manifest_schema": manifest_schema(),
        "next_action": "review_current_manifest"
        if manifest
        else "write_dependency_manifest",
        "instructions": (
            "Declare software prerequisites before writing the plan, minting children or signing off. "
            "Assess the brief and repository; do not interpret a missing declaration as no dependencies. "
            "The observed environment is the local check executor identity, not proof of the intended target. "
            "Use it for local checks; specify a different fully identified target when appropriate. "
            "Write every field in manifest_schema with expected_revision; actual_environment may be null. "
            "Set none_required=true and dependencies=[] only after explicitly assessing that no software is needed. "
            "Existing-installation verification requires no approval. Installation still requires separate current human authority."
        ),
    }
