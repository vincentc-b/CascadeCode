"""Durable, mutation-free admission for review-resolution actions.

Both a human request and the epic_031 recovery path describe the same review
action.  Keeping that normalization here makes the admission key independent
of which path happened to observe the problem first.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping
from urllib.parse import urlsplit

from cascade.workspace.integration_worktree import locate_trunk

ResolutionRequestSource = Literal["operator", "epic_031_recovery"]


def _required(value: object, name: str) -> str:
    """Return a safe required metadata value without changing any state."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    result = value.strip()
    if "\n" in result or "\r" in result:
        raise ValueError(f"{name} must be a single line")
    return result


def _ref(value: object, name: str) -> str:
    result = _required(value, name)
    if any(char.isspace() for char in result) or result.startswith("-"):
        raise ValueError(f"{name} is not an authorized ref")
    return result


def _review_url(value: object) -> str:
    url = _required(value, "review_url")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("review_url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password:
        raise ValueError("review_url must not contain credentials")
    return url


@dataclass(frozen=True)
class ResolutionActionRequest:
    """Validated identity and attribution needed before any resolution mutation.

    ``requester`` and ``assignee`` are deliberately not part of the identity:
    an operator nudge and an epic_031 recovery notification for the same
    observed review must reuse one durable action.
    """

    review_id: str
    review_url: str
    source_ref: str
    target_ref: str
    observed_source_head: str
    observed_target_head: str
    requester: str
    assignee: str
    source: ResolutionRequestSource
    review_state: str = "open"

    def __post_init__(self) -> None:
        object.__setattr__(self, "review_id", _required(self.review_id, "review_id"))
        object.__setattr__(self, "review_url", _review_url(self.review_url))
        object.__setattr__(self, "source_ref", _ref(self.source_ref, "source_ref"))
        object.__setattr__(self, "target_ref", _ref(self.target_ref, "target_ref"))
        object.__setattr__(
            self,
            "observed_source_head",
            _required(self.observed_source_head, "observed_source_head"),
        )
        object.__setattr__(
            self,
            "observed_target_head",
            _required(self.observed_target_head, "observed_target_head"),
        )
        object.__setattr__(self, "requester", _required(self.requester, "requester"))
        object.__setattr__(self, "assignee", _required(self.assignee, "assignee"))
        if self.source not in {"operator", "epic_031_recovery"}:
            raise ValueError("source must be operator or epic_031_recovery")
        if self.source_ref == self.target_ref:
            raise ValueError("source_ref and target_ref must differ")
        if self.review_state != "open":
            raise ValueError("review must be open for resolution admission")

    @property
    def idempotency_key(self) -> str:
        """Stable key for the observed review action, not for its submitter."""

        identity = {
            "kind": "review_resolution",
            "review_id": self.review_id,
            "source_ref": self.source_ref,
            "target_ref": self.target_ref,
            "observed_source_head": self.observed_source_head,
            "observed_target_head": self.observed_target_head,
        }
        encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        return "resolution:v1:" + hashlib.sha256(encoded).hexdigest()

    def as_dict(self) -> dict[str, str]:
        return {
            "review_id": self.review_id,
            "review_url": self.review_url,
            "source_ref": self.source_ref,
            "target_ref": self.target_ref,
            "observed_source_head": self.observed_source_head,
            "observed_target_head": self.observed_target_head,
            "requester": self.requester,
            "assignee": self.assignee,
            "source": self.source,
            "review_state": self.review_state,
        }


def _field(payload: Mapping[str, object], *names: str) -> object:
    for name in names:
        if name in payload:
            return payload[name]
    return None


def _normalize(
    payload: Mapping[str, object], *, source: ResolutionRequestSource
) -> ResolutionActionRequest:
    """Adapt either legacy-shaped input to the single typed contract.

    This function only validates and constructs an immutable request.  It does
    not write a registry, inspect Git, or otherwise grant mutation capability.
    """

    review = payload.get("review")
    review_data = review if isinstance(review, Mapping) else payload
    assignment = payload.get("assignment")
    assignment_data = assignment if isinstance(assignment, Mapping) else payload
    return ResolutionActionRequest(
        review_id=_field(review_data, "review_id", "id", "number"),  # type: ignore[arg-type]
        review_url=_field(review_data, "review_url", "url"),  # type: ignore[arg-type]
        source_ref=_field(review_data, "source_ref", "source_branch"),  # type: ignore[arg-type]
        target_ref=_field(review_data, "target_ref", "target_branch"),  # type: ignore[arg-type]
        observed_source_head=_field(
            payload, "observed_source_head", "source_head", "source_sha"
        ),  # type: ignore[arg-type]
        observed_target_head=_field(
            payload, "observed_target_head", "target_head", "target_sha"
        ),  # type: ignore[arg-type]
        requester=_field(payload, "requester", "actor", "requested_by"),  # type: ignore[arg-type]
        assignee=_field(
            assignment_data, "assignee", "assigned_team", "owner"
        ),  # type: ignore[arg-type]
        source=source,
        review_state=str(_field(review_data, "review_state", "state") or "open").lower(),
    )


def normalize_operator_request(payload: Mapping[str, object]) -> ResolutionActionRequest:
    """Normalize an explicit operator request without admitting or mutating it."""

    return _normalize(payload, source="operator")


def normalize_epic_031_recovery_request(payload: Mapping[str, object]) -> ResolutionActionRequest:
    """Normalize epic_031 recovery evidence into the same request contract."""

    return _normalize(payload, source="epic_031_recovery")


@dataclass(frozen=True)
class ResolutionActionAdmission:
    """The persisted action selected by one admission attempt."""

    action_id: str
    idempotency_key: str
    action: dict[str, object]
    reused: bool


@dataclass(frozen=True)
class ReviewContextBlocker:
    """A read-only reason that a resolution action has no safe owner yet."""

    code: str
    message: str
    affected_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedReviewContext:
    """The minimum immutable evidence needed by later admission checks.

    This model deliberately carries paths and observed heads, but it neither
    opens a shell nor changes the review, worktree, or action state.
    """

    review_id: str
    review_url: str
    source_ref: str
    target_ref: str
    authorized_refs: tuple[str, str]
    observed_source_head: str
    observed_target_head: str
    review_owner_id: str
    owning_scope: str
    accountable_team: str
    worktree: Path | None
    inspection_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ReviewContextResolution:
    """Exactly one accountable context or a concrete non-mutating blocker."""

    context: ResolvedReviewContext | None = None
    blocker: ReviewContextBlocker | None = None

    def __post_init__(self) -> None:
        if (self.context is None) == (self.blocker is None):
            raise ValueError("resolution must contain exactly one context or blocker")


def _resolution_blocker(code: str, message: str, *paths: Path) -> ReviewContextResolution:
    return ReviewContextResolution(
        blocker=ReviewContextBlocker(
            code=code,
            message=message,
            affected_paths=tuple(str(path) for path in paths),
        )
    )


def _review_records(trunk: Path) -> dict[str, dict[str, object]]:
    """Read the review registry without reusing its private write helpers."""

    path = trunk / ".cascade" / "reviews.json"
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        str(owner_id): dict(record)
        for owner_id, record in raw.items()
        if isinstance(record, dict)
    } if isinstance(raw, dict) else {}


def _matching_review_owners(
    request: ResolutionActionRequest, records: Mapping[str, Mapping[str, object]]
) -> list[tuple[str, Mapping[str, object]]]:
    """Match durable review identity before using its branch evidence."""

    matches: list[tuple[str, Mapping[str, object]]] = []
    for owner_id, record in records.items():
        url = str(record.get("url") or record.get("review_url") or "").strip()
        number = str(record.get("number") or "").strip()
        if url != request.review_url and number != request.review_id:
            continue
        state = str(record.get("state") or record.get("forge_state") or "").lower()
        if (
            bool(record.get("closed"))
            or state in {"closed", "merged"}
            or record.get("stage") == "completed"
        ):
            continue
        matches.append((owner_id, record))
    return matches


def _team_assignment(value: str) -> tuple[str, str] | None:
    """Parse the only two team identities accepted by this routing slice."""

    kind, separator, work_id = value.partition(":")
    if separator and kind in {"feature", "epic"} and work_id:
        return kind, work_id
    return None


def resolve_review_context(
    request: ResolutionActionRequest, *, root: Path
) -> ReviewContextResolution:
    """Resolve durable review evidence to one team without performing mutation.

    Registry identity is authoritative: a request cannot supply a different
    ref pair or use an arbitrary assignee to take ownership of another review.
    A child review may explicitly be escalated to its parent Epic Team.
    """

    trunk = locate_trunk(Path(root).resolve())
    records = _review_records(trunk)
    matches = _matching_review_owners(request, records)
    registry_path = trunk / ".cascade" / "reviews.json"
    if not matches:
        return _resolution_blocker(
            "open_review_not_found",
            "No open durable review matches the requested review identity.",
            registry_path,
        )
    if len(matches) != 1:
        return _resolution_blocker(
            "ambiguous_review_identity",
            "More than one open review matches this request; select one review explicitly.",
            registry_path,
        )

    owner_id, record = matches[0]
    source_ref = str(record.get("source_branch") or "")
    target_ref = str(record.get("target_branch") or "")
    if (source_ref, target_ref) != (request.source_ref, request.target_ref):
        return _resolution_blocker(
            "unauthorized_review_refs",
            "Requested refs do not match the open review's authorized ref pair.",
            registry_path,
        )

    from cascade.workspace.integration_worktree import get_integration_worktree, merged_board

    board = merged_board(trunk)
    owner = board.by_id.get(owner_id)
    if owner is None or owner.tier not in {"feature", "epic"}:
        return _resolution_blocker(
            "review_owner_metadata_missing",
            "The open review has no resolvable Feature or Epic owner.",
            registry_path,
        )

    team_kind = owner.tier
    team_id = owner.id
    assignment = _team_assignment(request.assignee)
    if assignment is None:
        return _resolution_blocker(
            "invalid_team_assignment",
            "The request assignee is not a Feature Team or Epic Team identity.",
        )
    assigned_kind, assigned_id = assignment
    if assigned_kind == "feature":
        if owner.tier != "feature" or assigned_id != owner.id:
            return _resolution_blocker(
                "unauthorized_team_assignment",
                "Only the owning Feature Team may resolve this feature review.",
            )
    elif owner.tier == "epic":
        if assigned_id != owner.id:
            return _resolution_blocker(
                "unauthorized_team_assignment",
                "Only the owning Epic Team may resolve this epic review.",
            )
    elif owner.parent != assigned_id:
        return _resolution_blocker(
            "ambiguous_cross_feature_owner",
            "A child review can route to an Epic Team only when it names its parent Epic.",
        )
    else:
        team_kind, team_id = assigned_kind, assigned_id

    team = board.by_id.get(team_id)
    if team is None or team.tier != team_kind:
        return _resolution_blocker(
            "assigned_team_metadata_missing",
            "The selected accountable team no longer exists in the board.",
        )

    kind = "feature" if team_kind == "feature" else "epic"
    entry = get_integration_worktree(trunk, kind, team_id)
    worktree = entry.path if entry is not None else None
    inspection_paths = [registry_path, owner.path, team.path]
    if worktree is not None:
        inspection_paths.append(worktree)
    return ReviewContextResolution(
        context=ResolvedReviewContext(
            review_id=request.review_id,
            review_url=request.review_url,
            source_ref=request.source_ref,
            target_ref=request.target_ref,
            authorized_refs=(source_ref, target_ref),
            observed_source_head=request.observed_source_head,
            observed_target_head=request.observed_target_head,
            review_owner_id=owner.id,
            owning_scope=f"{owner.tier}:{owner.id}",
            accountable_team=f"{team_kind}:{team_id}",
            worktree=worktree,
            inspection_paths=tuple(dict.fromkeys(inspection_paths)),
        )
    )


def _state_path(root: Path) -> Path:
    return root / ".cascade" / "resolution_actions.json"


def _load(path: Path) -> dict[str, dict[str, object]]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _save(path: Path, state: dict[str, dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=".resolution-actions.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            handle.write(json.dumps(state, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)


@contextmanager
def _write_lock(path: Path):
    lock_path = path.with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def admit_resolution_action(
    request: ResolutionActionRequest, *, root: Path
) -> ResolutionActionAdmission:
    """Persist a validated request once, or return the existing action unchanged."""

    trunk = locate_trunk(Path(root).resolve())
    path = _state_path(trunk)
    key = request.idempotency_key
    with _write_lock(path):
        state = _load(path)
        existing = state.get(key)
        if isinstance(existing, dict):
            return ResolutionActionAdmission(key, key, dict(existing), reused=True)
        action: dict[str, object] = {
            "action_id": key,
            "idempotency_key": key,
            "status": "admitted",
            "request": request.as_dict(),
        }
        state[key] = action
        _save(path, state)
        return ResolutionActionAdmission(key, key, dict(action), reused=False)


def resolution_action(action_id: str, *, root: Path) -> dict[str, object] | None:
    """Read one admitted action without changing its state."""

    state = _load(_state_path(locate_trunk(Path(root).resolve())))
    action = state.get(action_id)
    return dict(action) if isinstance(action, dict) else None
