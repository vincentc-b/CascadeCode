"""Revision-bound Epic Manager / Epic Architect plan sign-offs (epic_015 task_015_001_001)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.comments.store import read_comments
from cascade.comments.slug import section_slug
from cascade.board.gitutil import has_git, last_commit_touching
from cascade.board.lock import process_lock
from cascade.board.store import read_doc
from cascade.workspace.doc_root import resolve_doc_worktree
from cascade.workspace.integration_worktree import locate_trunk, merged_board

PlanningRole = Literal["epic_manager", "epic_architect"]
PlanningSignOffActor = PlanningRole | Literal["human"]

REQUIRED_PLANNING_ROLES: frozenset[PlanningRole] = frozenset(
    ("epic_manager", "epic_architect")
)

OPEN_QUESTIONS_SECTION = section_slug("Open questions")

_SIDECAR_DIR = Path("docs") / "epics" / "2_active" / "_planning_signoffs"
_SCHEMA_VERSION = 1
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


@dataclass(frozen=True, slots=True)
class PlanSignOff:
    role: PlanningRole
    plan_revision: str
    signed_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "plan_revision": self.plan_revision,
            "signed_at": self.signed_at.astimezone(timezone.utc).isoformat(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> PlanSignOff | None:
        role = raw.get("role")
        plan_revision = raw.get("plan_revision")
        signed_at = raw.get("signed_at")
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
        return cls(role=role, plan_revision=plan_revision, signed_at=parsed)


def sidecar_path(epic_id: str, *, root: Path) -> Path:
    repo = _signoff_repo(epic_id, root=root)
    return repo / _SIDECAR_DIR / f"{epic_id}.json"


def canonical_plan_revision(epic_id: str, *, root: Path) -> str | None:
    """Git SHA of the last commit that touched the epic plan document."""

    repo = _signoff_repo(epic_id, root=root)
    doc = read_doc(epic_id, root=repo)
    if doc.sha:
        return doc.sha
    if not has_git(repo):
        return None
    rel = doc.meta.path.resolve().relative_to(repo.resolve())
    return last_commit_touching(repo, rel)


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
    seen: set[tuple[PlanningRole, str]] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        record = PlanSignOff.from_dict(row)
        if record is None:
            continue
        key = (record.role, record.plan_revision)
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


def current_valid_sign_offs(epic_id: str, *, root: Path) -> dict[PlanningRole, PlanSignOff]:
    """Sign-offs that satisfy readiness for the epic's current canonical plan revision."""

    revision = canonical_plan_revision(epic_id, root=root)
    if revision is None:
        return {}
    return valid_sign_offs_for_revision(read_plan_sign_offs(epic_id, root=root), revision)


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
            raise UnauthorizedPlanningSignOff(
                f"{actor!r} cannot sign off for {role!r}"
            )

    repo = resolve_root(root)
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

    newly_signed = record_plan_sign_off(epic_id, role, canonical, root=repo)
    valid = current_valid_sign_offs(epic_id, root=repo)
    return {
        "ok": True,
        "epic_id": epic_id,
        "role": role,
        "plan_revision": canonical,
        "newly_signed": newly_signed,
        "sign_offs": {
            signed_role: row.to_dict() for signed_role, row in valid.items()
        },
    }


def record_plan_sign_off(
    epic_id: str,
    role: PlanningRole,
    plan_revision: str,
    *,
    root: Path,
    signed_at: datetime | None = None,
) -> bool:
    """Persist one role sign-off for ``plan_revision``. Returns False when idempotent."""

    if role not in REQUIRED_PLANNING_ROLES:
        raise InvalidPlanningRole(f"invalid planning role {role!r}")
    if not _SHA_RE.match(plan_revision):
        raise PlanSignOffError(f"invalid plan_revision {plan_revision!r}")

    when = signed_at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)

    path = sidecar_path(epic_id, root=root)
    with process_lock:
        existing = read_plan_sign_offs(epic_id, root=root)
        if any(row.role == role and row.plan_revision == plan_revision for row in existing):
            return False
        updated = (*existing, PlanSignOff(role=role, plan_revision=plan_revision, signed_at=when))
        _write_sidecar(path, updated)
    return True


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
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _signoff_repo(epic_id: str, *, root: Path) -> Path:
    trunk = locate_trunk(resolve_root(root))
    try:
        return resolve_doc_worktree(epic_id, root=trunk)
    except NotFound:
        return trunk
