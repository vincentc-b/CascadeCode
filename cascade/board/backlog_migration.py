"""Preflight planning for backlog epic hierarchical ID migration (feat_010 / task_021)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from cascade.board.errors import BoardError, SchemaError
from cascade.board.paths import column_for_status, infer_repo_root, slugify
from cascade.board.store import list_board, read_doc
from cascade.board.types import BoardIndex, WorkId, WorkMeta, WorkTier
from cascade.board.work_ids import (
    feature_id_key,
    format_hierarchical_epic_id,
    format_hierarchical_feature_id,
    format_hierarchical_task_id,
    parse_work_id_parts,
    validate_work_id_identity,
)
from cascade.workspace.integration_worktree import (
    branch_exists,
    integration_branch,
    integration_worktree_path,
    load_registry,
)

_BACKLOG_STATUSES = frozenset({"backlog", "ready_to_plan"})
_BACKLOG_FOLDER = "1_backlog"
_WORK_ID_TOKEN = re.compile(
    r"\b(?:epic_\d{3}|feat_\d{3}(?:_\d{3})?|task_\d{3}(?:_\d{3}_\d{3})?)\b"
)
_MARKDOWN_LINK = re.compile(
    r"\]\(((?:\.\./)*docs/(?:epics|features|tasks)/[^)]+\.md)\)"
)
_KIND_FOR_TIER: dict[WorkTier, str] = {"epic": "epic", "feature": "feature", "task": "task"}


class BacklogMigrationValidationError(BoardError):
    """Migration preflight failed; ``errors`` is sorted for deterministic reporting."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(sorted(set(errors)))
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True, slots=True)
class ReferenceUpdate:
    """One board-owned structured reference that must change when applying the plan."""

    path: Path
    owner_id: WorkId
    location: str
    old_value: str
    new_value: str


@dataclass(frozen=True, slots=True)
class PathUpdate:
    old_path: Path
    new_path: Path


@dataclass(frozen=True, slots=True)
class BacklogMigrationPlan:
    """Validated dry-run plan. Applying it is implemented in task_022."""

    scoped_ids: frozenset[WorkId]
    id_mapping: tuple[tuple[WorkId, WorkId], ...]
    path_updates: tuple[PathUpdate, ...]
    reference_updates: tuple[ReferenceUpdate, ...]
    sidecar_renames: tuple[PathUpdate, ...]
    runtime_checks: tuple[str, ...]

    @property
    def renames(self) -> tuple[tuple[WorkId, WorkId], ...]:
        return tuple(pair for pair in self.id_mapping if pair[0] != pair[1])


def build_backlog_migration_plan(*, root: Path) -> BacklogMigrationPlan:
    """Discover backlog epic graphs, assign target IDs, and validate without writing."""

    repo = Path(root).resolve()
    board = list_board(repo)
    errors: list[str] = []

    scoped = _discover_scoped_ids(board, errors)
    if errors:
        raise BacklogMigrationValidationError(errors)

    if not scoped:
        return BacklogMigrationPlan(
            scoped_ids=frozenset(),
            id_mapping=(),
            path_updates=(),
            reference_updates=(),
            sidecar_renames=(),
            runtime_checks=_runtime_check_labels(),
        )

    _validate_scoped_status(board, scoped, errors)
    _validate_scoped_hierarchy(board, scoped, errors)
    runtime_blockers = _runtime_artifact_blockers(repo, board, scoped)
    errors.extend(runtime_blockers)

    mapping = _assign_target_ids(board, scoped, errors)
    if errors:
        raise BacklogMigrationValidationError(errors)

    full_pairs = tuple(sorted((old, new) for old, new in mapping.items()))
    path_updates = _path_updates(board, mapping)
    reference_updates = _reference_updates(repo, board, mapping, scoped)
    sidecar_renames = _sidecar_renames(repo, mapping)
    sidecar_refs = _comment_sidecar_reference_updates(repo, sidecar_renames, mapping)
    reference_updates = tuple(
        sorted(
            reference_updates + sidecar_refs,
            key=lambda row: (str(row.path), row.location, row.old_value),
        )
    )

    inbound_errors = _inbound_reference_errors(board, mapping, scoped)
    if inbound_errors:
        raise BacklogMigrationValidationError(inbound_errors)

    collision_errors = _target_collision_errors(board, mapping)
    if collision_errors:
        raise BacklogMigrationValidationError(collision_errors)

    for old_id, new_id in mapping.items():
        if old_id == new_id:
            continue
        meta = board.by_id[old_id]
        try:
            validate_work_id_identity(new_id, tier=meta.tier, parent=_mapped_parent(meta, mapping))
        except SchemaError as exc:
            errors.append(f"{old_id} -> {new_id}: {exc}")

    if errors:
        raise BacklogMigrationValidationError(errors)

    return BacklogMigrationPlan(
        scoped_ids=scoped,
        id_mapping=full_pairs,
        path_updates=path_updates,
        reference_updates=reference_updates,
        sidecar_renames=sidecar_renames,
        runtime_checks=_runtime_check_labels(),
    )


def _discover_scoped_ids(board: BoardIndex, errors: list[str]) -> frozenset[WorkId]:
    backlog_epics: set[WorkId] = set()
    for work_id, meta in board.by_id.items():
        if meta.tier != "epic":
            continue
        if meta.path.parent.name != _BACKLOG_FOLDER:
            continue
        backlog_epics.add(work_id)

    scoped: set[WorkId] = set(backlog_epics)
    for work_id, meta in board.by_id.items():
        if meta.tier == "feature" and meta.parent in backlog_epics:
            scoped.add(work_id)
    feature_scope = {wid for wid in scoped if board.by_id[wid].tier == "feature"}
    for work_id, meta in board.by_id.items():
        if meta.tier == "task" and meta.parent in feature_scope:
            scoped.add(work_id)

    for work_id in sorted(scoped):
        meta = board.by_id.get(work_id)
        if meta is None:
            errors.append(f"missing board entry for scoped id {work_id}")
    return frozenset(scoped)


def _validate_scoped_status(board: BoardIndex, scoped: frozenset[WorkId], errors: list[str]) -> None:
    for work_id in sorted(scoped):
        meta = board.by_id[work_id]
        if meta.status not in _BACKLOG_STATUSES:
            errors.append(
                f"{work_id} has status {meta.status!r}; backlog migration requires backlog-only work"
            )
        if meta.path.parent.name != _BACKLOG_FOLDER:
            errors.append(
                f"{work_id} lives in {meta.path.parent.name}; expected {_BACKLOG_FOLDER}"
            )
        if meta.integration_branch or meta.integration_worktree:
            errors.append(f"{work_id} has integration metadata; retire runtime artifacts first")


def _validate_scoped_hierarchy(board: BoardIndex, scoped: frozenset[WorkId], errors: list[str]) -> None:
    for work_id in sorted(scoped):
        meta = board.by_id[work_id]
        if meta.tier == "epic":
            if meta.parent is not None:
                errors.append(f"{work_id} epic must not have a parent")
            continue
        if not meta.parent:
            errors.append(f"{work_id} requires a parent")
            continue
        if meta.parent not in board.by_id:
            errors.append(f"{work_id} parent {meta.parent} is not on the board")
            continue
        if meta.tier == "feature" and board.by_id[meta.parent].tier != "epic":
            errors.append(f"{work_id} parent {meta.parent} is not an epic")
        if meta.tier == "task" and board.by_id[meta.parent].tier != "feature":
            errors.append(f"{work_id} parent {meta.parent} is not a feature")


def _runtime_check_labels() -> tuple[str, ...]:
    return (
        "integration_worktree_registry",
        "integration_branch",
        "integration_worktree_path",
        "langgraph_checkpoint",
        "event_queue_sidecar",
    )


def _runtime_artifact_blockers(repo: Path, board: BoardIndex, scoped: frozenset[WorkId]) -> list[str]:
    blockers: list[str] = []
    for entry in load_registry(repo):
        if entry.work_id in scoped:
            blockers.append(
                f"{entry.work_id} is registered in the integration worktree registry"
            )

    for work_id in sorted(scoped):
        meta = board.by_id[work_id]
        kind = _KIND_FOR_TIER[meta.tier]
        branch = integration_branch(kind, work_id)  # type: ignore[arg-type]
        if branch_exists(repo, branch):
            blockers.append(f"integration branch {branch!r} exists for {work_id}")
        wt_path = integration_worktree_path(kind, work_id, trunk=repo)  # type: ignore[arg-type]
        if wt_path.is_dir():
            blockers.append(f"integration worktree directory exists for {work_id}")
        checkpoint = repo / ".cascade" / "checkpoints" / f"{work_id}.sqlite"
        if checkpoint.is_file():
            blockers.append(f"LangGraph checkpoint exists for {work_id}")
        queue = repo / "docs" / "_queue" / f"{work_id}.jsonl"
        if queue.is_file():
            blockers.append(f"event queue sidecar exists for {work_id}")
    return blockers


def _assign_target_ids(
    board: BoardIndex,
    scoped: frozenset[WorkId],
    errors: list[str],
) -> dict[WorkId, WorkId]:
    mapping: dict[WorkId, WorkId] = {work_id: work_id for work_id in scoped}

    backlog_epics = sorted(wid for wid in scoped if board.by_id[wid].tier == "epic")
    for epic_id in backlog_epics:
        try:
            epic_num = parse_work_id_parts(epic_id).segments[0]
        except SchemaError as exc:
            errors.append(f"{epic_id}: {exc}")
            continue
        target_epic = format_hierarchical_epic_id(epic_num)
        mapping[epic_id] = target_epic

        features = sorted(
            wid
            for wid in scoped
            if board.by_id[wid].tier == "feature" and board.by_id[wid].parent == epic_id
        )
        reserved_features = _reserved_feature_numbers(board, epic_id, epic_num, scoped)
        next_feature = 1
        for feature_id in features:
            mapped = _map_feature_id(
                feature_id,
                board=board,
                epic_num=epic_num,
                reserved=reserved_features,
                next_start=next_feature,
                errors=errors,
            )
            if mapped is None:
                continue
            new_id, next_feature = mapped
            mapping[feature_id] = new_id
            reserved_features.add(parse_work_id_parts(new_id).segments[1])

        for feature_id in features:
            if feature_id not in mapping:
                continue
            feature_target = mapping[feature_id]
            try:
                feat_epic, feat_num = feature_id_key(feature_target)
            except SchemaError as exc:
                errors.append(f"{feature_id}: {exc}")
                continue
            tasks = sorted(
                wid
                for wid in scoped
                if board.by_id[wid].tier == "task" and board.by_id[wid].parent == feature_id
            )
            reserved_tasks = _reserved_task_numbers(board, feature_id, feat_epic, feat_num, scoped)
            next_task = 1
            for task_id in tasks:
                mapped = _map_task_id(
                    task_id,
                    board=board,
                    epic_num=feat_epic,
                    feature_num=feat_num,
                    reserved=reserved_tasks,
                    next_start=next_task,
                    errors=errors,
                )
                if mapped is None:
                    continue
                new_id, next_task = mapped
                mapping[task_id] = new_id
                reserved_tasks.add(parse_work_id_parts(new_id).segments[2])

    return mapping


def _reserved_feature_numbers(
    board: BoardIndex,
    epic_id: WorkId,
    epic_num: int,
    scoped: frozenset[WorkId],
) -> set[int]:
    reserved: set[int] = set()
    for work_id, meta in board.by_id.items():
        if meta.tier != "feature" or meta.parent != epic_id:
            continue
        if work_id in scoped:
            parsed = parse_work_id_parts(work_id)
            if parsed.form == "hierarchical" and parsed.segments[0] == epic_num:
                reserved.add(parsed.segments[1])
            continue
        parsed = parse_work_id_parts(work_id)
        if parsed.form == "hierarchical" and parsed.segments[0] == epic_num:
            reserved.add(parsed.segments[1])
        elif parsed.form == "legacy":
            reserved.add(parsed.segments[0])
    return reserved


def _reserved_task_numbers(
    board: BoardIndex,
    feature_id: WorkId,
    epic_num: int,
    feature_num: int,
    scoped: frozenset[WorkId],
) -> set[int]:
    reserved: set[int] = set()
    for work_id, meta in board.by_id.items():
        if meta.tier != "task" or meta.parent != feature_id:
            continue
        if work_id in scoped:
            parsed = parse_work_id_parts(work_id)
            if (
                parsed.form == "hierarchical"
                and parsed.segments[0] == epic_num
                and parsed.segments[1] == feature_num
            ):
                reserved.add(parsed.segments[2])
            continue
        parsed = parse_work_id_parts(work_id)
        if (
            parsed.form == "hierarchical"
            and parsed.segments[0] == epic_num
            and parsed.segments[1] == feature_num
        ):
            reserved.add(parsed.segments[2])
        elif parsed.form == "legacy":
            reserved.add(parsed.segments[0])
    return reserved


def _map_feature_id(
    feature_id: WorkId,
    *,
    board: BoardIndex,
    epic_num: int,
    reserved: set[int],
    next_start: int,
    errors: list[str],
) -> tuple[WorkId, int] | None:
    try:
        parsed = parse_work_id_parts(feature_id)
    except SchemaError as exc:
        errors.append(f"{feature_id}: {exc}")
        return None
    if parsed.form == "hierarchical":
        if parsed.segments[0] != epic_num:
            errors.append(
                f"{feature_id} hierarchical epic segment {parsed.segments[0]:03d} "
                f"does not match parent epic epic_{epic_num:03d}"
            )
            return None
        return feature_id, max(next_start, parsed.segments[1] + 1)

    num = next_start
    while num in reserved or format_hierarchical_feature_id(epic_num, num) in board.by_id:
        num += 1
    if num > 999:
        errors.append(f"no free feature segment for {feature_id} under epic_{epic_num:03d}")
        return None
    return format_hierarchical_feature_id(epic_num, num), num + 1


def _map_task_id(
    task_id: WorkId,
    *,
    board: BoardIndex,
    epic_num: int,
    feature_num: int,
    reserved: set[int],
    next_start: int,
    errors: list[str],
) -> tuple[WorkId, int] | None:
    try:
        parsed = parse_work_id_parts(task_id)
    except SchemaError as exc:
        errors.append(f"{task_id}: {exc}")
        return None
    if parsed.form == "hierarchical":
        if parsed.segments[0] != epic_num or parsed.segments[1] != feature_num:
            errors.append(
                f"{task_id} segments do not match parent feature "
                f"feat_{epic_num:03d}_{feature_num:03d}"
            )
            return None
        return task_id, max(next_start, parsed.segments[2] + 1)

    num = next_start
    candidate = format_hierarchical_task_id(epic_num, feature_num, num)
    while num in reserved or candidate in board.by_id:
        num += 1
        candidate = format_hierarchical_task_id(epic_num, feature_num, num)
    if num > 999:
        errors.append(
            f"no free task segment for {task_id} under feat_{epic_num:03d}_{feature_num:03d}"
        )
        return None
    return candidate, num + 1


def _mapped_parent(meta: WorkMeta, mapping: dict[WorkId, WorkId]) -> WorkId | None:
    if meta.parent is None:
        return None
    return mapping.get(meta.parent, meta.parent)


def _path_updates(board: BoardIndex, mapping: dict[WorkId, WorkId]) -> tuple[PathUpdate, ...]:
    updates: list[PathUpdate] = []
    for old_id, new_id in sorted(mapping.items()):
        if old_id == new_id:
            continue
        meta = board.by_id[old_id]
        new_path = _renamed_doc_path(meta.path, old_id, new_id)
        updates.append(PathUpdate(old_path=meta.path, new_path=new_path))
    return tuple(updates)


def _renamed_doc_path(path: Path, old_id: WorkId, new_id: WorkId) -> Path:
    stem = path.stem
    if stem == old_id:
        new_stem = new_id
    elif stem.startswith(old_id + "_"):
        new_stem = new_id + stem[len(old_id) :]
    else:
        slug = slugify(stem)
        new_stem = f"{new_id}_{slug}"
    return path.with_name(new_stem + path.suffix)


def _reference_updates(
    repo: Path,
    board: BoardIndex,
    mapping: dict[WorkId, WorkId],
    scoped: frozenset[WorkId],
) -> tuple[ReferenceUpdate, ...]:
    changing = {old: new for old, new in mapping.items() if old != new}
    if not changing:
        return ()

    updates: list[ReferenceUpdate] = []
    for work_id in sorted(scoped):
        doc = read_doc(work_id, root=repo)
        updates.extend(_meta_reference_updates(doc.meta, changing))
        updates.extend(_body_reference_updates(doc.meta.path, work_id, doc.body, changing))

    for work_id, meta in sorted(board.by_id.items()):
        if work_id in scoped:
            continue
        updates.extend(_meta_reference_updates(meta, changing, owner_id=work_id))

    return tuple(sorted(updates, key=lambda row: (str(row.path), row.location, row.old_value)))


def _meta_reference_updates(
    meta: WorkMeta,
    changing: dict[WorkId, WorkId],
    *,
    owner_id: WorkId | None = None,
) -> list[ReferenceUpdate]:
    owner = owner_id or meta.id
    rows: list[ReferenceUpdate] = []
    if meta.id in changing:
        rows.append(
            ReferenceUpdate(
                path=meta.path,
                owner_id=owner,
                location="meta.id",
                old_value=meta.id,
                new_value=changing[meta.id],
            )
        )
    if meta.parent and meta.parent in changing:
        rows.append(
            ReferenceUpdate(
                path=meta.path,
                owner_id=owner,
                location="meta.parent",
                old_value=meta.parent,
                new_value=changing[meta.parent],
            )
        )
    for index, child in enumerate(meta.children):
        if child in changing:
            rows.append(
                ReferenceUpdate(
                    path=meta.path,
                    owner_id=owner,
                    location=f"meta.children[{index}]",
                    old_value=child,
                    new_value=changing[child],
                )
            )
    for index, dep in enumerate(meta.depends_on):
        if dep in changing:
            rows.append(
                ReferenceUpdate(
                    path=meta.path,
                    owner_id=owner,
                    location=f"meta.depends_on[{index}]",
                    old_value=dep,
                    new_value=changing[dep],
                )
            )
    for index, cite in enumerate(meta.cites):
        if cite in changing:
            rows.append(
                ReferenceUpdate(
                    path=meta.path,
                    owner_id=owner,
                    location=f"meta.cites[{index}]",
                    old_value=cite,
                    new_value=changing[cite],
                )
            )
    return rows


def _body_reference_updates(
    path: Path,
    owner_id: WorkId,
    body: str,
    changing: dict[WorkId, WorkId],
) -> list[ReferenceUpdate]:
    rows: list[ReferenceUpdate] = []
    for line_no, line in enumerate(body.splitlines(), start=1):
        for match in _WORK_ID_TOKEN.finditer(line):
            token = match.group(0)
            if token not in changing:
                continue
            rows.append(
                ReferenceUpdate(
                    path=path,
                    owner_id=owner_id,
                    location=f"body:{line_no}",
                    old_value=token,
                    new_value=changing[token],
                )
            )
        for match in _MARKDOWN_LINK.finditer(line):
            link_path = match.group(1)
            for old_id, new_id in changing.items():
                if old_id in link_path:
                    rows.append(
                        ReferenceUpdate(
                            path=path,
                            owner_id=owner_id,
                            location=f"body:{line_no}:link",
                            old_value=link_path,
                            new_value=link_path.replace(old_id, new_id),
                        )
                    )
    return rows


def _sidecar_renames(repo: Path, mapping: dict[WorkId, WorkId]) -> tuple[PathUpdate, ...]:
    updates: list[PathUpdate] = []
    comments_dir = repo / "docs" / "_comments"
    if not comments_dir.is_dir():
        return ()
    for old_id, new_id in sorted(mapping.items()):
        if old_id == new_id:
            continue
        old_path = comments_dir / f"{old_id}.jsonl"
        if not old_path.is_file():
            continue
        updates.append(
            PathUpdate(old_path=old_path, new_path=comments_dir / f"{new_id}.jsonl")
        )
    return tuple(updates)


def _inbound_reference_errors(
    board: BoardIndex,
    mapping: dict[WorkId, WorkId],
    scoped: frozenset[WorkId],
) -> list[str]:
    changing = {old: new for old, new in mapping.items() if old != new}
    if not changing:
        return []

    errors: list[str] = []
    for work_id, meta in sorted(board.by_id.items()):
        if work_id in scoped:
            continue
        if column_for_status(meta.status) == "backlog" or meta.status == "ready_to_plan":
            continue
        refs = _meta_outbound_refs(meta, changing)
        if refs:
            errors.append(
                f"{work_id} references migrated backlog id(s) {', '.join(sorted(refs))}; "
                "active/completed work must remain unchanged"
            )
            continue
        repo = infer_repo_root(meta.path)
        if repo is None:
            continue
        doc = read_doc(work_id, root=repo)
        for row in _body_reference_updates(meta.path, work_id, doc.body, changing):
            errors.append(
                f"{work_id} references migrated backlog id {row.old_value!r} in {row.location}; "
                "active/completed work must remain unchanged"
            )
            break
    return errors


def _comment_sidecar_reference_updates(
    repo: Path,
    sidecar_renames: tuple[PathUpdate, ...],
    mapping: dict[WorkId, WorkId],
) -> tuple[ReferenceUpdate, ...]:
    changing = {old: new for old, new in mapping.items() if old != new}
    rows: list[ReferenceUpdate] = []
    seen = {update.old_path for update in sidecar_renames}
    for path in sorted(seen):
        rows.extend(scan_comment_sidecar_references(path, changing))
    return tuple(rows)


def _meta_outbound_refs(meta: WorkMeta, changing: dict[WorkId, WorkId]) -> set[WorkId]:
    refs: set[WorkId] = set()
    if meta.parent and meta.parent in changing:
        refs.add(meta.parent)
    for child in meta.children:
        if child in changing:
            refs.add(child)
    for dep in meta.depends_on:
        if dep in changing:
            refs.add(dep)
    for cite in meta.cites:
        if cite in changing:
            refs.add(cite)
    return refs


def _target_collision_errors(board: BoardIndex, mapping: dict[WorkId, WorkId]) -> list[str]:
    errors: list[str] = []
    targets: dict[WorkId, WorkId] = {}
    for old_id, new_id in sorted(mapping.items()):
        if old_id == new_id:
            continue
        if new_id in board.by_id and new_id != old_id:
            occupant = board.by_id[new_id]
            errors.append(f"target id {new_id} already occupied by {occupant.path}")
        other = targets.get(new_id)
        if other is not None and other != old_id:
            errors.append(f"id collision: {old_id} and {other} both map to {new_id}")
        targets[new_id] = old_id

    for old_id, new_id in mapping.items():
        if old_id == new_id:
            continue
        new_path = _renamed_doc_path(board.by_id[old_id].path, old_id, new_id)
        for other_id, other_meta in board.by_id.items():
            if other_id == old_id:
                continue
            if other_meta.path.resolve() == new_path.resolve():
                errors.append(
                    f"path collision: {new_id} would occupy {new_path} already used by {other_id}"
                )
    return errors


def scan_comment_sidecar_references(path: Path, changing: dict[WorkId, WorkId]) -> list[ReferenceUpdate]:
    """Return structured reference updates needed inside a comment JSONL sidecar."""

    if not path.is_file() or not changing:
        return []
    owner_id = path.stem
    rows: list[ReferenceUpdate] = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        doc_id = payload.get("doc_id")
        if isinstance(doc_id, str) and doc_id in changing:
            rows.append(
                ReferenceUpdate(
                    path=path,
                    owner_id=owner_id,
                    location=f"sidecar:{line_no}:doc_id",
                    old_value=doc_id,
                    new_value=changing[doc_id],
                )
            )
        for field in ("parent",):
            value = payload.get(field)
            if isinstance(value, str) and value in changing:
                rows.append(
                    ReferenceUpdate(
                        path=path,
                        owner_id=owner_id,
                        location=f"sidecar:{line_no}:{field}",
                        old_value=value,
                        new_value=changing[value],
                    )
                )
        blocks = payload.get("blocks")
        if isinstance(blocks, list):
            for index, block in enumerate(blocks):
                if isinstance(block, str) and block in changing:
                    rows.append(
                        ReferenceUpdate(
                            path=path,
                            owner_id=owner_id,
                            location=f"sidecar:{line_no}:blocks[{index}]",
                            old_value=block,
                            new_value=changing[block],
                        )
                    )
    return rows
