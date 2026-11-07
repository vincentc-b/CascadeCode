"""Human dependency/bootstrap actions exposed through the War Room API."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Mapping

from cascade.board.lock import process_lock
from cascade.epic.dependency_approvals import (
    AuthenticatedHuman,
    DependencyApprovalError,
    approve_dependency_installations,
)
from cascade.epic.dependency_bootstrap import (
    BootstrapScope,
    DependencyBootstrapError,
    StaleBootstrapRevision,
    authorize_feasibility,
    read_bootstrap,
)
from cascade.epic.dependency_manifests import (
    DependencyManifestError,
    InstallationBinding,
    InvalidDependencyManifest,
    require_dependency_manifest,
)
from cascade.epic.dependency_resume import (
    DependencyResumeError,
    resume_dependency_bootstrap,
)
from cascade.epic.dependency_status import project_dependency_status
from cascade.task.action_recovery import ActionRecoveryError

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler


BOOTSTRAP_REVIEW_PATH = "/api/review_dependency_bootstrap"
INSTALLATION_APPROVAL_PATH = "/api/approve_dependency_installations"
PING_TEAM_PATH = "/api/ping_dependency_team"


def register_dependency_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_post_route(BOOTSTRAP_REVIEW_PATH, handle_bootstrap_review)
    handler_cls.register_post_route(
        INSTALLATION_APPROVAL_PATH, handle_installation_approval
    )
    handler_cls.register_post_route(PING_TEAM_PATH, handle_ping_team)


def handle_bootstrap_review(
    handler: WarRoomRequestHandler, body: dict[str, Any]
) -> None:
    epic_id = _epic_id(body)
    human = _authenticated_human(handler, epic_id)
    if epic_id is None or human is None:
        return
    expected_revision = body.get("bootstrap_revision")
    fingerprint = body.get("scope_fingerprint")
    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 1
        or not isinstance(fingerprint, str)
        or not fingerprint
        or "scope" not in body
    ):
        _refuse(
            handler,
            HTTPStatus.BAD_REQUEST,
            "invalid_bootstrap_review",
            "bootstrap_revision, scope_fingerprint, and the complete reviewed scope are required",
            epic_id,
        )
        return
    try:
        reviewed_scope = BootstrapScope.from_dict(body["scope"])
    except (DependencyBootstrapError, InvalidDependencyManifest) as exc:
        _refuse(handler, HTTPStatus.BAD_REQUEST, "invalid_bootstrap_scope", str(exc), epic_id)
        return

    try:
        # Manifest/scope comparison and journal append share the canonical
        # process lock, so a concurrent manifest write cannot authorize an
        # obsolete review.
        with process_lock:
            manifest = require_dependency_manifest(epic_id, root=handler.server.root)
            current = read_bootstrap(epic_id, root=handler.server.root)
            if current is None:
                raise DependencyBootstrapError(
                    f"{epic_id} has no bootstrap scope to review"
                )
            if current.scope.manifest_revision != manifest.revision:
                raise StaleBootstrapRevision(
                    "bootstrap scope is stale for the current manifest"
                )
            if (
                current.revision != expected_revision
                or current.scope.fingerprint != fingerprint
                or current.scope != reviewed_scope
            ):
                raise StaleBootstrapRevision(
                    "submitted bootstrap scope is stale; refresh and review the current scope"
                )
            snapshot = authorize_feasibility(
                epic_id,
                tuple(row.artifact_id for row in current.scope.feasibility_artifacts),
                authorizer=human,
                root=handler.server.root,
                expected_revision=current.revision,
            )
    except StaleBootstrapRevision as exc:
        _refuse(handler, HTTPStatus.CONFLICT, "stale_bootstrap_scope", str(exc), epic_id)
        return
    except (DependencyBootstrapError, DependencyManifestError) as exc:
        _refuse(handler, HTTPStatus.BAD_REQUEST, "bootstrap_review_refused", str(exc), epic_id)
        return

    _accepted(
        handler,
        epic_id,
        {
            "bootstrap_revision": snapshot.revision,
            "authorization": (
                snapshot.authorization.to_dict() if snapshot.authorization else None
            ),
        },
    )


def handle_installation_approval(
    handler: WarRoomRequestHandler, body: dict[str, Any]
) -> None:
    epic_id = _epic_id(body)
    human = _authenticated_human(handler, epic_id)
    if epic_id is None or human is None:
        return
    revision = body.get("manifest_revision")
    rows = body.get("entries")
    if (
        isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
        or not isinstance(rows, list)
        or not rows
    ):
        _refuse(
            handler,
            HTTPStatus.BAD_REQUEST,
            "invalid_installation_review",
            "manifest_revision and a non-empty entries list are required",
            epic_id,
        )
        return
    try:
        bindings = tuple(_reviewed_binding(row) for row in rows)
    except (DependencyApprovalError, InvalidDependencyManifest) as exc:
        _refuse(handler, HTTPStatus.BAD_REQUEST, "invalid_installation_binding", str(exc), epic_id)
        return
    expected = {row.dependency_id: row for row in bindings}
    if len(expected) != len(bindings):
        _refuse(
            handler,
            HTTPStatus.BAD_REQUEST,
            "duplicate_dependency",
            "a dependency may appear only once per approval batch",
            epic_id,
        )
        return
    try:
        approvals = approve_dependency_installations(
            epic_id,
            tuple(row.dependency_id for row in bindings),
            approver=human,
            root=handler.server.root,
            expected_manifest_revision=revision,
            expected_bindings=expected,
        )
    except DependencyApprovalError as exc:
        detail = str(exc)
        status = HTTPStatus.CONFLICT if "stale" in detail else HTTPStatus.BAD_REQUEST
        _refuse(handler, status, "installation_approval_refused", detail, epic_id)
        return
    except DependencyManifestError as exc:
        _refuse(handler, HTTPStatus.BAD_REQUEST, "installation_approval_refused", str(exc), epic_id)
        return

    _accepted(
        handler,
        epic_id,
        {"approvals": [row.to_dict() for row in approvals]},
    )


def handle_ping_team(handler: WarRoomRequestHandler, body: dict[str, Any]) -> None:
    epic_id = _epic_id(body)
    human = _authenticated_human(handler, epic_id)
    if epic_id is None or human is None:
        return
    request_id = body.get("request_id")
    references = body.get("approval_references", {})
    if not isinstance(request_id, str) or not request_id.strip():
        _refuse(handler, HTTPStatus.BAD_REQUEST, "invalid_ping", "request_id is required", epic_id)
        return
    if not isinstance(references, Mapping) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in references.items()
    ):
        _refuse(
            handler,
            HTTPStatus.BAD_REQUEST,
            "invalid_ping",
            "approval_references must map dependency IDs to approval IDs",
            epic_id,
        )
        return
    executor = handler.server.dependency_executor
    if executor is None:
        _refuse(
            handler,
            HTTPStatus.SERVICE_UNAVAILABLE,
            "dependency_executor_unavailable",
            "no trusted bounded dependency executor is configured",
            epic_id,
        )
        return
    try:
        result = resume_dependency_bootstrap(
            epic_id,
            request_id,
            executor=executor,
            root=handler.server.root,
            approval_references=dict(references),
            requester=human,
        )
    except (DependencyResumeError, DependencyManifestError, ActionRecoveryError) as exc:
        _refuse(handler, HTTPStatus.CONFLICT, "ping_refused", str(exc), epic_id)
        return
    _accepted(handler, epic_id, {"ping": result.to_dict()})


def _reviewed_binding(raw: object) -> InstallationBinding:
    if not isinstance(raw, Mapping) or set(raw) != {"dependency_id", "binding"}:
        raise DependencyApprovalError(
            "each entry must contain dependency_id and the complete displayed binding"
        )
    dependency_id = raw.get("dependency_id")
    binding = InstallationBinding.from_dict(raw.get("binding"))
    if dependency_id != binding.dependency_id:
        raise DependencyApprovalError(
            "entry dependency_id does not match its installation binding"
        )
    return binding


def _epic_id(body: Mapping[str, object]) -> str | None:
    value = body.get("epic_id")
    return value if isinstance(value, str) and value.strip() else None


def _authenticated_human(
    handler: WarRoomRequestHandler, epic_id: str | None
) -> AuthenticatedHuman | None:
    if epic_id is None:
        _refuse(
            handler,
            HTTPStatus.BAD_REQUEST,
            "invalid_epic",
            "epic_id is required",
            None,
        )
        return None
    human = handler.server.authenticated_human
    if not isinstance(human, AuthenticatedHuman):
        _refuse(
            handler,
            HTTPStatus.UNAUTHORIZED,
            "human_authentication_required",
            "this authority-granting action requires a trusted authenticated human boundary",
            epic_id,
        )
        return None
    return human


def _accepted(
    handler: WarRoomRequestHandler, epic_id: str, extra: Mapping[str, object]
) -> None:
    handler._json_response(
        HTTPStatus.OK,
        {
            "ok": True,
            **extra,
            "dependency_status": project_dependency_status(
                epic_id, root=handler.server.root
            ),
        },
    )


def _refuse(
    handler: WarRoomRequestHandler,
    status: HTTPStatus,
    code: str,
    detail: str,
    epic_id: str | None,
) -> None:
    payload: dict[str, object] = {
        "ok": False,
        "refusal": {"code": code, "detail": detail},
    }
    if epic_id is not None:
        payload["dependency_status"] = project_dependency_status(
            epic_id, root=handler.server.root
        )
    handler._json_response(status, payload)
