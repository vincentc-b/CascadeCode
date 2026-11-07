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
import subprocess
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
class AdmissionBlocker:
    """Durable evidence explaining why an action cannot be mutated safely."""

    checkpoint: str
    code: str
    message: str
    observed_refs: tuple[str, str]
    observed_shas: tuple[str, str]
    affected_paths: tuple[str, ...]
    resume_action: str

    def as_dict(self) -> dict[str, object]:
        return {
            "checkpoint": self.checkpoint,
            "code": self.code,
            "message": self.message,
            "observed_refs": list(self.observed_refs),
            "observed_shas": list(self.observed_shas),
            "affected_paths": list(self.affected_paths),
            "resume_action": self.resume_action,
        }


@dataclass(frozen=True)
class MutationReadyHandoff:
    """Evidence a later mutation-only slice may consume; this slice does not mutate."""

    action_id: str
    review_id: str
    accountable_team: str
    worktree: str
    authorized_refs: tuple[str, str]
    observed_shas: tuple[str, str]

    def as_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "review_id": self.review_id,
            "accountable_team": self.accountable_team,
            "worktree": self.worktree,
            "authorized_refs": list(self.authorized_refs),
            "observed_shas": list(self.observed_shas),
            "mutation_performed": False,
        }


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


def _admission_blocker(
    context: ResolvedReviewContext | None,
    *,
    checkpoint: str,
    code: str,
    message: str,
    resume_action: str,
    paths: tuple[Path, ...] = (),
) -> AdmissionBlocker:
    refs = context.authorized_refs if context is not None else ("", "")
    shas = (
        (context.observed_source_head, context.observed_target_head)
        if context is not None
        else ("", "")
    )
    return AdmissionBlocker(
        checkpoint=checkpoint,
        code=code,
        message=message,
        observed_refs=refs,
        observed_shas=shas,
        affected_paths=tuple(str(path) for path in paths),
        resume_action=resume_action,
    )


def _review_record(context: ResolvedReviewContext, *, root: Path) -> dict[str, object] | None:
    """Read only the registry already named in the resolved inspection surface."""

    registry = next(
        (path for path in context.inspection_paths if path.name == "reviews.json"), None
    )
    if registry is None or registry.resolve() != (root / ".cascade" / "reviews.json").resolve():
        return None
    return _review_records(root).get(context.review_owner_id)


def _bool_metadata(record: Mapping[str, object], *names: str) -> bool | None:
    """Accept the small set of explicit boolean capability markers we persist/read."""

    for name in names:
        value = record.get(name)
        if isinstance(value, bool):
            return value
    return None


def _live_sha(worktree: Path, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=worktree,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _is_ancestor(worktree: Path, ancestor: str, descendant: str) -> bool:
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=worktree, capture_output=True, text=True, encoding="utf-8",
    )
    return result.returncode == 0


def _dirty_paths(worktree: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=worktree,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return (str(worktree),)
    paths: list[str] = []
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].split(" -> ")[-1]
        # Cascade's own durable sidecars are expected to be untracked in an
        # integration checkout and are not operator edits needing recovery.
        if not path.startswith(".cascade/"):
            paths.append(path)
    return tuple(paths)


def _evaluate_admission(
    request: ResolutionActionRequest, context: ResolvedReviewContext, *, root: Path
) -> AdmissionBlocker | MutationReadyHandoff:
    """Run safety checks using only paths named by context resolution.

    The review registry is the scoped forge snapshot for this boundary.  Git
    reads are limited to the resolved worktree and the two authorized refs.
    Nothing here changes Git, the review, or a worktree.
    """

    record = _review_record(context, root=root)
    registry = root / ".cascade" / "reviews.json"
    if record is None:
        return _admission_blocker(
            context, checkpoint="metadata", code="review_metadata_missing",
            message="The resolved review metadata is unavailable.",
            resume_action="Restore the open review registry record, then submit the action again.",
            paths=(registry,),
        )
    state = str(record.get("state") or record.get("forge_state") or "open").lower()
    if bool(record.get("closed")) or state in {"closed", "merged"} or record.get("stage") == "completed":
        return _admission_blocker(
            context, checkpoint="review_open", code="review_closed",
            message="The review is no longer open for conflict resolution.",
            resume_action="Open a new review action only if a new open review requires resolution.",
            paths=(registry,),
        )
    if tuple(context.authorized_refs) != (request.source_ref, request.target_ref):
        return _admission_blocker(
            context, checkpoint="authorized_refs", code="unauthorized_review_refs",
            message="The request refs no longer match the resolved review refs.",
            resume_action="Refresh the review context and submit its authorized ref pair.",
            paths=(registry,),
        )
    credentials = _bool_metadata(record, "credentials_available", "credential_available")
    if credentials is False:
        return _admission_blocker(
            context, checkpoint="credentials", code="credentials_unavailable",
            message="Credentials required to resolve this review are unavailable.",
            resume_action="Restore the review credentials, then retry admission.", paths=(registry,),
        )
    permissions = _bool_metadata(record, "resolution_permitted", "permissions_available", "can_resolve")
    if permissions is False:
        return _admission_blocker(
            context, checkpoint="permissions", code="insufficient_permissions",
            message="The accountable team lacks permission to resolve this review.",
            resume_action="Grant review-resolution permission to the accountable team, then retry.",
            paths=(registry,),
        )
    if context.worktree is None or context.worktree not in context.inspection_paths:
        return _admission_blocker(
            context, checkpoint="metadata", code="worktree_metadata_missing",
            message="No scoped integration worktree is available for safe inspection.",
            resume_action="Restore the accountable team's integration worktree, then retry admission.",
        )
    worktree = context.worktree
    if not worktree.is_dir():
        return _admission_blocker(
            context, checkpoint="metadata", code="worktree_unavailable",
            message="The resolved integration worktree is unavailable.",
            resume_action="Restore the registered integration worktree, then retry admission.",
            paths=(worktree,),
        )
    source_sha = _live_sha(worktree, context.authorized_refs[0])
    target_sha = _live_sha(worktree, context.authorized_refs[1])
    if source_sha is None or target_sha is None:
        return _admission_blocker(
            context, checkpoint="metadata", code="observed_head_metadata_missing",
            message="The resolved worktree cannot read both authorized review heads.",
            resume_action="Fetch or restore the authorized refs, then retry admission.", paths=(worktree,),
        )
    source_matches = source_sha == context.observed_source_head
    source_is_resolved_ahead = bool(
        source_sha
        and context.observed_source_head != context.observed_target_head
        and _is_ancestor(worktree, context.observed_source_head, source_sha)
        and _is_ancestor(worktree, context.observed_target_head, source_sha)
    )
    if target_sha != context.observed_target_head or not (source_matches or source_is_resolved_ahead):
        return _admission_blocker(
            context, checkpoint="observed_heads", code="stale_observed_heads",
            message="The live authorized refs no longer match the observed review heads or a clean local resolution containing both observed heads.",
            resume_action="Refresh review heads and submit a new resolution action.", paths=(worktree,),
        )
    dirty = _dirty_paths(worktree)
    if dirty:
        return _admission_blocker(
            context, checkpoint="worktree_clean", code="dirty_unrelated_paths",
            message="The scoped worktree contains uncommitted paths unrelated to this action.",
            resume_action="Commit, stash, or discard the listed paths before retrying admission.",
            paths=tuple(worktree / path for path in dirty),
        )
    return MutationReadyHandoff(
        action_id=request.idempotency_key,
        review_id=context.review_id,
        accountable_team=context.accountable_team,
        worktree=str(worktree),
        authorized_refs=context.authorized_refs,
        observed_shas=(source_sha, target_sha),
    )


def admit_resolution_action(
    request: ResolutionActionRequest, *, root: Path
) -> ResolutionActionAdmission:
    """Persist one safe handoff or actionable blocker; never perform mutation."""

    trunk = locate_trunk(Path(root).resolve())
    path = _state_path(trunk)
    key = request.idempotency_key
    with _write_lock(path):
        state = _load(path)
        existing = state.get(key)
        if isinstance(existing, dict):
            return ResolutionActionAdmission(key, key, dict(existing), reused=True)
        resolution = resolve_review_context(request, root=trunk)
        action: dict[str, object] = {
            "action_id": key,
            "idempotency_key": key,
            "request": request.as_dict(),
        }
        if resolution.blocker is not None:
            blocker = AdmissionBlocker(
                checkpoint="context_resolution",
                code=resolution.blocker.code,
                message=resolution.blocker.message,
                observed_refs=(request.source_ref, request.target_ref),
                observed_shas=(request.observed_source_head, request.observed_target_head),
                affected_paths=resolution.blocker.affected_paths,
                resume_action="Resolve the review context shown by the affected paths, then retry admission.",
            )
            action.update(status="blocked", blocker=blocker.as_dict())
        else:
            assert resolution.context is not None
            outcome = _evaluate_admission(request, resolution.context, root=trunk)
            if isinstance(outcome, AdmissionBlocker):
                action.update(status="blocked", blocker=outcome.as_dict())
            else:
                action.update(status="mutation_ready", handoff=outcome.as_dict())
        state[key] = action
        _save(path, state)
        return ResolutionActionAdmission(key, key, dict(action), reused=False)


def resolution_action(action_id: str, *, root: Path) -> dict[str, object] | None:
    """Read one admitted action without changing its state."""

    state = _load(_state_path(locate_trunk(Path(root).resolve())))
    action = state.get(action_id)
    return dict(action) if isinstance(action, dict) else None
