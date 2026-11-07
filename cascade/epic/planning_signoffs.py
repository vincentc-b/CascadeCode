"""Revision-bound Epic Manager / Epic Architect plan sign-offs (epic_015 task_015_001_001)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cascade.board.context import resolve_tracking_root
from cascade.board.errors import NotFound
from cascade.comments.store import read_comments
from cascade.comments.slug import section_slug
from cascade.board.gitutil import commit_paths, has_git, last_commit_touching
from cascade.board.lock import process_lock
from cascade.board.store import read_doc
from cascade.board.types import WorkMeta
from cascade.workspace.doc_root import resolve_doc_worktree
from cascade.workspace.integration_worktree import locate_trunk, merged_board

PlanningRole = Literal["epic_manager", "epic_architect"]
PlanningSignOffActor = PlanningRole | Literal["human"]

REQUIRED_PLANNING_ROLES: frozenset[PlanningRole] = frozenset(
    ("epic_manager", "epic_architect")
)

OPEN_QUESTIONS_SECTION = section_slug("Open questions")

_SIDECAR_DIR = Path("docs") / "epics" / "2_active" / "_planning_signoffs"
_SCHEMA_VERSION = 2
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


class PlanSignOffError(Exception):
    """Invalid plan sign-off operation."""


class InvalidPlanningRole(PlanSignOffError):
    """Role is not a required planning sign-off role."""


class UnauthorizedPlanningSignOff(PlanSignOffError):
    """Agent attempted to sign off for a role other than its own."""


class StalePlanRevision(PlanSignOffError):
    """Client expected plan revision no longer matches the canonical revision."""


class UnresolvedOpenQuestions(PlanSignOffError):
    """Epic still has open canonical open-question threads."""


class DependenciesNotReady(PlanSignOffError):
    """Current dependency manifest/evidence does not permit planning."""


@dataclass(frozen=True, slots=True)
class PlanSignOff:
    role: PlanningRole
    plan_revision: str
    signed_at: datetime
    evidence_snapshot_id: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "plan_revision": self.plan_revision,
            "signed_at": self.signed_at.astimezone(timezone.utc).isoformat(),
            "evidence_snapshot_id": self.evidence_snapshot_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PlanSignOff | None:
        role = raw.get("role")
        plan_revision = raw.get("plan_revision")
        signed_at = raw.get("signed_at")
        evidence_snapshot_id = raw.get("evidence_snapshot_id")
        if role not in REQUIRED_PLANNING_ROLES:
            return None
        if not isinstance(plan_revision, str) or not _SHA_RE.match(plan_revision):
            return None
        if not isinstance(signed_at, str):
            return None
        try:
            parsed = datetime.fromisoformat(signed_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        if evidence_snapshot_id is not None and (
            not isinstance(evidence_snapshot_id, str)
            or not evidence_snapshot_id.strip()
        ):
            return None
        return cls(
            role=role,
            plan_revision=plan_revision,
            signed_at=parsed,
            evidence_snapshot_id=evidence_snapshot_id,
        )


def sidecar_path(epic_id: str, *, root: Path) -> Path:
    repo = _signoff_repo(epic_id, root=root)
    return repo / _SIDECAR_DIR / f"{epic_id}.json"


def canonical_plan_revision(
    epic_id: str, *, root: Path, meta: WorkMeta | None = None
) -> str | None:
    """Git SHA of the last commit that touched the epic plan document."""

    repo = _signoff_repo(epic_id, root=root)
    if meta is not None:
        try:
            rel = meta.path.resolve().relative_to(repo.resolve())
        except ValueError:
            pass
        else:
            if has_git(repo):
                return last_commit_touching(repo, rel)
            try:
                content = meta.path.read_bytes()
            except OSError:
                return None
            return hashlib.sha1(content).hexdigest()

    doc = read_doc(epic_id, root=repo)
    if doc.sha:
        return doc.sha
    if has_git(repo):
        rel = doc.meta.path.resolve().relative_to(repo.resolve())
        return last_commit_touching(repo, rel)
    try:
        content = doc.meta.path.read_bytes()
    except OSError:
        return None
    return hashlib.sha1(content).hexdigest()


def read_plan_sign_offs(epic_id: str, *, root: Path) -> tuple[PlanSignOff, ...]:
    """Load all stored sign-offs for ``epic_id`` (any revision)."""

    path = sidecar_path(epic_id, root=root)
    if not path.is_file():
        return ()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return ()
    if not isinstance(payload, dict):
        return ()
    rows = payload.get("sign_offs")
    if not isinstance(rows, list):
        return ()
    parsed: list[PlanSignOff] = []
    seen: set[tuple[PlanningRole, str, str | None]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        record = PlanSignOff.from_dict(row)
        if record is None:
            continue
        key = (record.role, record.plan_revision, record.evidence_snapshot_id)
        if key in seen:
            continue
        seen.add(key)
        parsed.append(record)
    return tuple(parsed)


def valid_sign_offs_for_revision(
    sign_offs: tuple[PlanSignOff, ...],
    plan_revision: str,
) -> dict[PlanningRole, PlanSignOff]:
    """Return at most one sign-off per role bound to ``plan_revision``."""

    hits: dict[PlanningRole, PlanSignOff] = {}
    for row in sign_offs:
        if row.plan_revision != plan_revision:
            continue
        hits[row.role] = row
    return hits


def current_valid_sign_offs(
    epic_id: str,
    *,
    root: Path,
    plan_revision: str | None = None,
) -> dict[PlanningRole, PlanSignOff]:
    """Sign-offs that satisfy readiness for the epic's current canonical plan revision."""

    revision = plan_revision or canonical_plan_revision(epic_id, root=root)
    if revision is None:
        return {}
    from cascade.epic.dependency_evidence import dependency_evidence_snapshot_is_current

    valid: dict[PlanningRole, PlanSignOff] = {}
    for row in read_plan_sign_offs(epic_id, root=root):
        if (
            row.plan_revision == revision
            and row.evidence_snapshot_id is not None
            and dependency_evidence_snapshot_is_current(
                epic_id, row.evidence_snapshot_id, root=root
            )
        ):
            valid[row.role] = row
    return valid


def unresolved_canonical_open_questions(epic_id: str, *, root: Path) -> tuple[str, ...]:
    """Open root comment ids anchored to the epic's Open questions section."""

    hits: list[str] = []
    for row in read_comments(epic_id, root=root):
        if row.parent is not None:
            continue
        if row.state != "open":
            continue
        if section_slug(row.section) != OPEN_QUESTIONS_SECTION:
            continue
        hits.append(row.id)
    return tuple(hits)


def sign_off_epic_plan(
    epic_id: str,
    role: PlanningRole,
    plan_revision: str,
    *,
    root: Path,
    actor: PlanningSignOffActor = "human",
) -> dict[str, object]:
    """Record the caller's planning-role sign-off for the current canonical revision."""

    if role not in REQUIRED_PLANNING_ROLES:
        raise InvalidPlanningRole(f"invalid planning role {role!r}")
    if actor != "human":
        if actor not in REQUIRED_PLANNING_ROLES:
            raise InvalidPlanningRole(f"invalid planning actor {actor!r}")
        if actor != role:
            raise UnauthorizedPlanningSignOff(f"{actor!r} cannot sign off for {role!r}")

    repo = _signoff_repo(epic_id, root=root)
    board = merged_board(repo)
    meta = board.by_id.get(epic_id)
    if meta is None or meta.tier != "epic":
        raise PlanSignOffError(f"{epic_id} is not an active epic")
    if meta.path.parent.name != "2_active":
        raise PlanSignOffError("epic plan sign-off requires an active epic team")
    if meta.plan_approved_at is not None:
        raise PlanSignOffError(f"epic plan for {epic_id} is already approved")

    canonical = canonical_plan_revision(epic_id, root=repo)
    if canonical is None:
        raise PlanSignOffError(f"canonical plan revision unavailable for {epic_id}")
    if plan_revision != canonical:
        raise StalePlanRevision(
            f"stale plan revision for {epic_id}: canonical is {canonical}, expected {plan_revision}"
        )

    open_questions = unresolved_canonical_open_questions(epic_id, root=repo)
    if open_questions:
        joined = ", ".join(open_questions)
        raise UnresolvedOpenQuestions(
            f"unresolved open question(s) on {epic_id}: {joined}"
        )

    from cascade.epic.dependency_evidence import (
        compute_dependency_readiness,
        create_dependency_evidence_snapshot,
    )

    dependency_readiness = compute_dependency_readiness(epic_id, root=repo)
    if not dependency_readiness.ready:
        details = ", ".join(
            f"{row.reason}:{row.dependency_id or 'manifest'}"
            for row in dependency_readiness.blockers
        )
        raise DependenciesNotReady(f"dependencies_not_ready ({details})")
    existing_valid = current_valid_sign_offs(
        epic_id, root=repo, plan_revision=canonical
    )
    if role in existing_valid:
        snapshot_id = existing_valid[role].evidence_snapshot_id
        newly_signed = False
    else:
        evidence_snapshot = create_dependency_evidence_snapshot(epic_id, root=repo)
        snapshot_id = evidence_snapshot.snapshot_id
        newly_signed = record_plan_sign_off(
            epic_id,
            role,
            canonical,
            root=repo,
            evidence_snapshot_id=snapshot_id,
        )
    valid = current_valid_sign_offs(epic_id, root=repo)
    return {
        "ok": True,
        "epic_id": epic_id,
        "role": role,
        "plan_revision": canonical,
        "newly_signed": newly_signed,
        "evidence_snapshot_id": snapshot_id,
        "sign_offs": {signed_role: row.to_dict() for signed_role, row in valid.items()},
    }


def record_plan_sign_off(
    epic_id: str,
    role: PlanningRole,
    plan_revision: str,
    *,
    root: Path,
    signed_at: datetime | None = None,
    evidence_snapshot_id: str | None = None,
) -> bool:
    """Persist one role sign-off for ``plan_revision``. Returns False when idempotent."""

    if role not in REQUIRED_PLANNING_ROLES:
        raise InvalidPlanningRole(f"invalid planning role {role!r}")
    if not _SHA_RE.match(plan_revision):
        raise PlanSignOffError(f"invalid plan_revision {plan_revision!r}")

    when = signed_at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    if evidence_snapshot_id is None:
        existing_valid = current_valid_sign_offs(
            epic_id, root=root, plan_revision=plan_revision
        )
        if role in existing_valid:
            return False
        from cascade.epic.dependency_evidence import create_dependency_evidence_snapshot

        evidence_snapshot_id = create_dependency_evidence_snapshot(
            epic_id, root=root
        ).snapshot_id

    path = sidecar_path(epic_id, root=root)
    with process_lock:
        existing = read_plan_sign_offs(epic_id, root=root)
        if any(
            row.role == role
            and row.plan_revision == plan_revision
            and row.evidence_snapshot_id == evidence_snapshot_id
            for row in existing
        ):
            return False
        updated = (
            *existing,
            PlanSignOff(
                role=role,
                plan_revision=plan_revision,
                signed_at=when,
                evidence_snapshot_id=evidence_snapshot_id,
            ),
        )
        _write_sidecar(path, updated)
        _commit_sidecar(epic_id, path, root=root, role=role)
    return True


def _commit_sidecar(
    epic_id: str,
    path: Path,
    *,
    root: Path,
    role: PlanningRole,
) -> None:
    repo = _signoff_repo(epic_id, root=root)
    if not has_git(repo):
        return
    from cascade.workspace.integration_worktree import (
        git_root_for_path,
        invalidate_merged_board,
        locate_trunk,
    )

    commit_root = git_root_for_path(path)
    commit_paths(
        commit_root,
        [path],
        f"docs: {epic_id} plan sign-off ({role})",
    )
    invalidate_merged_board(locate_trunk(repo))


def hydrate_plan_sign_offs(epic_id: str, *, root: Path) -> None:
    """Ensure an empty sidecar exists for active, unapproved epics (migration default)."""

    repo = _signoff_repo(epic_id, root=root)
    doc = read_doc(epic_id, root=repo)
    if doc.meta.tier != "epic":
        raise PlanSignOffError(f"{epic_id} is not an epic")
    if doc.meta.plan_approved_at is not None:
        return
    if doc.meta.path.parent.name != "2_active":
        return
    path = sidecar_path(epic_id, root=root)
    if path.is_file():
        return
    with process_lock:
        if path.is_file():
            return
        _write_sidecar(path, ())


def _write_sidecar(path: Path, sign_offs: tuple[PlanSignOff, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _SCHEMA_VERSION,
        "sign_offs": [row.to_dict() for row in sign_offs],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _signoff_repo(epic_id: str, *, root: Path) -> Path:
    trunk = locate_trunk(resolve_tracking_root(root))
    try:
        return resolve_doc_worktree(epic_id, root=trunk)
    except NotFound:
        return trunk
