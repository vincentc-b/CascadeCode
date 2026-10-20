"""Sole path to roster model turns (feat_014 kickoff gates)."""

from __future__ import annotations

import contextvars
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.workspace.types import KickoffReason

_model_turn_authorized: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_model_turn_authorized",
    default=False,
)

_default_root: Path | None = None

_COMMENT_KICKOFF_CONTENT_CAP = 2000
_COMMENT_KICKOFF_SIDECAR_NOTE = (
    "\n(Full text in the comment sidecar; use read_doc and thread comments.)"
)
_COMMENT_QUEUE_TYPES = frozenset({"CommentPosted", "CommentReplied", "CommentResolved"})


def model_turn_authorized() -> bool:
    """True while ``kickoff_turn`` is executing a roster model invocation."""

    return _model_turn_authorized.get()


def install_kickoff(root: Path) -> None:
    """Remember repo root for kickoff calls that omit ``reason.root``."""

    global _default_root
    _default_root = Path(root).resolve()


def kickoff_turn(reason: KickoffReason) -> None:
    """Run at most one roster model turn for an authorized edge; fail closed on models."""

    repo = resolve_root(reason.root or _default_root)
    token = _model_turn_authorized.set(True)
    try:
        _kickoff_turn(reason, repo)
    finally:
        _model_turn_authorized.reset(token)


def resume_inflight_graphs(root: Path) -> None:
    """Continue interrupted turns only; idle graphs stay idle."""

    repo = Path(root).resolve()
    from cascade.workspace.integration_worktree import merged_board

    board = merged_board(repo)
    for work_id in sorted(board.by_id):
        meta = board.by_id[work_id]
        if meta.path.parent.name != "2_active":
            continue
        if meta.tier not in ("epic", "feature", "task"):
            continue
        if not _graph_has_inflight_turn(work_id, meta.tier, root=repo, feature_id=meta.parent):
            continue
        kickoff_turn(
            KickoffReason(
                kind="resume_inflight",
                work_id=work_id,
                by="watchdog",
                root=repo,
                feature_id=meta.parent if meta.tier == "task" else None,
            )
        )


def kickoff_human_comment(doc_id: str, comment_id: str, *, root: Path) -> bool:
    """Start one comment-kind turn for a human comment on an active owning graph."""

    from cascade.comments.store import CommentStoreError, read_comments
    from cascade.workspace.integration_worktree import merged_board

    repo = Path(root).resolve()
    try:
        record = next(
            (row for row in read_comments(doc_id, root=repo) if row.id == comment_id),
            None,
        )
    except CommentStoreError:
        return False
    if record is None or record.author != "human":
        return False

    board = merged_board(repo)
    meta = board.by_id.get(doc_id)
    if meta is None or meta.path.parent.name != "2_active":
        return False
    if meta.tier not in ("epic", "feature"):
        return False

    message = {"role": "human", "content": _comment_kickoff_content(record)}
    kickoff_turn(
        KickoffReason(
            kind="comment",
            work_id=doc_id,
            by="watchdog",
            root=repo,
            message=message,
        )
    )
    return True


def deliver_queue_kickoffs(root: Path) -> None:
    """Ingest new queue lines for live graphs and kick one turn when events arrived."""

    repo = Path(root).resolve()
    from cascade.watchdog.events import read_events
    from cascade.workspace.integration_worktree import merged_board

    board = merged_board(repo)
    for work_id in sorted(board.by_id):
        meta = board.by_id[work_id]
        if meta.path.parent.name != "2_active":
            continue
        if meta.tier not in ("epic", "feature", "task"):
            continue
        feature_id = meta.parent if meta.tier == "task" else None
        before = _queue_offset(work_id, meta.tier, root=repo, feature_id=feature_id)
        new_events, _ = read_events(work_id, before, root=repo)
        after_state = _ingest_queue_only(
            work_id,
            meta.tier,
            root=repo,
            feature_id=feature_id,
        )
        after = int(after_state.get("last_queue_offset") or 0)
        if after <= before:
            continue
        human_comments, has_non_comment = _classify_queue_events(new_events)
        for doc_id, comment_id in human_comments:
            kickoff_human_comment(doc_id, comment_id, root=repo)
        if has_non_comment:
            kickoff_turn(
                KickoffReason(
                    kind="queue_event",
                    work_id=work_id,
                    by="watchdog",
                    root=repo,
                    feature_id=feature_id,
                )
            )


def _comment_kickoff_content(record) -> str:
    blocking = " [blocking]" if record.blocking else ""
    header = f"{record.id} on {record.doc_id} #{record.section}{blocking}\n"
    body = record.body
    full = header + body
    if len(full) <= _COMMENT_KICKOFF_CONTENT_CAP:
        return full
    reserve = len(header) + len(_COMMENT_KICKOFF_SIDECAR_NOTE)
    max_body = _COMMENT_KICKOFF_CONTENT_CAP - reserve
    if max_body <= 0:
        return (header + _COMMENT_KICKOFF_SIDECAR_NOTE)[:_COMMENT_KICKOFF_CONTENT_CAP]
    trimmed = body[:max_body].rstrip()
    if len(body) > max_body:
        trimmed = f"{trimmed}…"
    return header + trimmed + _COMMENT_KICKOFF_SIDECAR_NOTE


def _classify_queue_events(events: list) -> tuple[list[tuple[str, str]], bool]:
    human_comments: list[tuple[str, str]] = []
    has_non_comment = False
    for event in events:
        if event.type in _COMMENT_QUEUE_TYPES:
            if event.type in ("CommentPosted", "CommentReplied"):
                if event.payload.get("author") == "human":
                    doc_id = event.payload.get("doc_id")
                    comment_id = event.payload.get("comment_id")
                    if isinstance(doc_id, str) and isinstance(comment_id, str):
                        human_comments.append((doc_id, comment_id))
            continue
        has_non_comment = True
    return human_comments, has_non_comment


def _kickoff_turn(reason: KickoffReason, repo: Path) -> None:
    from cascade.workspace.integration_worktree import doc_filesystem_root

    doc = None
    tier: str | None = None
    try:
        from cascade.board.errors import GitError
        from cascade.board.gitutil import has_git
        from cascade.workspace.integration_worktree import doc_filesystem_root

        if has_git(repo):
            doc_root = doc_filesystem_root(reason.work_id, trunk=repo)
        else:
            doc_root = repo
        doc = read_doc(reason.work_id, root=doc_root)
        tier = doc.meta.tier
    except (NotFound, GitError):
        tier = _tier_from_work_id(reason.work_id)
    if tier not in ("epic", "feature", "task"):
        return

    if reason.kind in ("human_message", "comment") and reason.message is not None:
        meta = doc.meta if doc is not None else None
        feature_id = reason.feature_id or (doc.meta.parent if doc else None)
        _stage_human_message(
            reason.work_id,
            tier,
            reason.message,
            root=repo,
            feature_id=feature_id,
            model_id=reason.model_id,
        )
        if not _ensure_role_models(
            reason.work_id,
            tier,
            meta,
            repo,
            reason.model_id,
            toast_on_failure=reason.kind in ("human_message", "comment"),
        ):
            return
        _invoke_role_turn(
            reason.work_id,
            tier,
            root=repo,
            feature_id=reason.feature_id or (doc.meta.parent if doc else None),
            model_id=reason.model_id,
        )
        return

    if reason.kind == "resume_inflight":
        if not _graph_has_inflight_turn(
            reason.work_id,
            tier,
            root=repo,
            feature_id=reason.feature_id or (doc.meta.parent if doc else None),
        ):
            return
        if not _checkpoint_has_models(reason.work_id, tier, root=repo, feature_id=reason.feature_id):
            return
        _invoke_role_turn(
            reason.work_id,
            tier,
            root=repo,
            feature_id=reason.feature_id or (doc.meta.parent if doc else None),
            model_id=reason.model_id,
            resume=True,
        )
        return

    if doc is None:
        return

    if reason.kind in ("activate", "dispatch", "queue_event"):
        if not _checkpoint_has_models(reason.work_id, tier, root=repo, feature_id=reason.feature_id):
            if reason.kind in ("activate", "dispatch"):
                if not _ensure_role_models(
                    reason.work_id,
                    tier,
                    doc.meta,
                    repo,
                    reason.model_id,
                    toast_on_failure=False,
                ):
                    return
            else:
                return
        if not _has_turn_input(
            reason.work_id,
            tier,
            root=repo,
            feature_id=reason.feature_id or doc.meta.parent,
        ):
            return
        _invoke_role_turn(
            reason.work_id,
            tier,
            root=repo,
            feature_id=reason.feature_id or doc.meta.parent,
            model_id=reason.model_id,
        )


def _tier_from_work_id(work_id: str) -> str | None:
    if work_id.startswith("epic_"):
        return "epic"
    if work_id.startswith("feat_"):
        return "feature"
    if work_id.startswith("task_"):
        return "task"
    return None


def _ensure_role_models(
    work_id: str,
    tier: str,
    meta,
    repo: Path,
    model_id: str | None,
    *,
    toast_on_failure: bool = False,
) -> bool:
    parent = meta.parent if meta is not None else None
    explicit_model = model_id is not None and str(model_id).strip()
    if _checkpoint_has_models(work_id, tier, root=repo, feature_id=parent):
        return True
    if meta is None and not explicit_model:
        return False
    doc_meta = meta
    from cascade.watchdog.boot_model import toast_model_config_failure
    from cascade.watchdog.config import ConfigError
    from cascade.agent.errors import ProviderConfigError
    from cascade.watchdog.model_resolve import (
        ModelConfigError,
        ResolvedBackend,
        ResolvedModel,
        resolve_backend,
        resolve_project_provider,
    )

    explicit_model_id = str(model_id).strip() if explicit_model else None

    def _with_explicit_model(role: str, backend: ResolvedBackend) -> ResolvedBackend:
        if explicit_model_id is None:
            return backend
        return ResolvedBackend(
            provider=backend.provider,
            provider_source=backend.provider_source,
            model=ResolvedModel(role=role, model_id=explicit_model_id, source="document"),  # type: ignore[arg-type]
        )

    def _provider_only_backend(role: str) -> ResolvedBackend:
        provider, provider_source = resolve_project_provider(doc_meta, root=repo)
        return ResolvedBackend(
            provider=provider,
            provider_source=provider_source,
            model=ResolvedModel(
                role=role,  # type: ignore[arg-type]
                model_id=explicit_model_id or "",
                source="document",
            ),
        )

    def _resolve_role_backend(role: str) -> ResolvedBackend:
        try:
            return _with_explicit_model(role, resolve_backend(role, doc_meta, root=repo))  # type: ignore[arg-type]
        except ModelConfigError:
            if explicit_model_id is None:
                raise
            backend = _provider_only_backend(role)
            if not backend.model.model_id:
                raise
            return backend

    try:
        if tier == "epic":
            from cascade.epic.graph import seed_epic_role_models

            manager = _resolve_role_backend("epic_manager")
            architect = _resolve_role_backend("epic_architect")
            seed_epic_role_models(
                work_id,
                manager=manager,
                architect=architect,
                root=repo,
            )
        elif tier == "feature":
            from cascade.feature.graph import seed_feature_role_models

            lead = _resolve_role_backend("feature_lead")
            architect = _resolve_role_backend("feature_architect")
            seed_feature_role_models(
                work_id,
                lead=lead,
                architect=architect,
                root=repo,
            )
        else:
            from cascade.task.graph import seed_task_role_models

            swe = _resolve_role_backend("swe")
            seed_task_role_models(
                work_id,
                swe=swe,
                root=repo,
                feature_id=parent,
            )
    except (ModelConfigError, ProviderConfigError, ConfigError) as exc:
        if toast_on_failure:
            toast_model_config_failure(work_id, str(exc), root=repo)
        return False
    return True


def _checkpoint_has_providers(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> bool:
    state = _graph_state(work_id, tier, root=root, feature_id=feature_id)
    if not state:
        return False
    provider_ids = state.get("provider_ids") or {}
    if tier == "epic":
        return bool(str(provider_ids.get("epic_manager") or "").strip()) and bool(
            str(provider_ids.get("epic_architect") or "").strip()
        )
    if tier == "feature":
        return bool(str(provider_ids.get("feature_lead") or "").strip()) and bool(
            str(provider_ids.get("feature_architect") or "").strip()
        )
    return bool(str(provider_ids.get("swe") or "").strip())


def _checkpoint_has_models(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> bool:
    if not _checkpoint_has_providers(work_id, tier, root=root, feature_id=feature_id):
        return False
    state = _graph_state(work_id, tier, root=root, feature_id=feature_id)
    if not state:
        return False
    if model_id_from_state(state) is not None:
        return True
    model_ids = state.get("model_ids") or {}
    if tier == "epic":
        return bool(str(model_ids.get("epic_manager") or "").strip()) and bool(
            str(model_ids.get("epic_architect") or "").strip()
        )
    if tier == "feature":
        return bool(str(model_ids.get("feature_lead") or "").strip()) and bool(
            str(model_ids.get("feature_architect") or "").strip()
        )
    return bool(str(model_ids.get("swe") or "").strip())


def model_id_from_state(state: dict) -> str | None:
    from cascade.agent.graph_turn import model_id_from_state as _from_graph

    return _from_graph(state)


def _has_turn_input(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> bool:
    from cascade.agent.graph_turn import latest_input

    state = _graph_state(work_id, tier, root=root, feature_id=feature_id)
    if not state:
        return False
    return latest_input(state.get("messages") or []) is not None


def _queue_offset(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> int:
    state = _graph_state(work_id, tier, root=root, feature_id=feature_id)
    if not state:
        return 0
    return int(state.get("last_queue_offset") or 0)


def _ingest_queue_only(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> dict:
    if tier == "epic":
        from cascade.epic.graph import ingest_queue

        return dict(ingest_queue(work_id, root=root))
    if tier == "feature":
        from cascade.feature.graph import ingest_queue

        return dict(ingest_queue(work_id, root=root))
    from cascade.task.graph import ingest_queue

    return dict(ingest_queue(work_id, root=root, feature_id=feature_id))


def _graph_state(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> dict | None:
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(work_id, root=root)
        config = thread_config(work_id)
    elif tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(work_id, root=root)
        config = thread_config(work_id)
    else:
        from cascade.task.checkpoint import thread_config
        from cascade.task.graph import ensure_task_graph

        graph = ensure_task_graph(work_id, root=root, feature_id=feature_id)
        config = thread_config(work_id)
    values = graph.get_state(config).values
    return dict(values) if values else None


def _graph_has_inflight_turn(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> bool:
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(work_id, root=root)
        config = thread_config(work_id)
    elif tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(work_id, root=root)
        config = thread_config(work_id)
    else:
        from cascade.task.checkpoint import thread_config
        from cascade.task.graph import ensure_task_graph

        graph = ensure_task_graph(work_id, root=root, feature_id=feature_id)
        config = thread_config(work_id)
    snapshot = graph.get_state(config)
    return bool(snapshot.next)


def _stage_human_message(
    work_id: str,
    tier: str,
    message: dict,
    *,
    root: Path,
    feature_id: str | None,
    model_id: str | None,
) -> None:
    payload: dict = {"messages": [message]}
    if model_id is not None:
        payload["model_id"] = model_id
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(work_id, root=root)
        config = thread_config(work_id)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            payload["epic_id"] = work_id
            payload["last_queue_offset"] = 0
        graph.update_state(config, payload)
        return
    if tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(work_id, root=root)
        config = thread_config(work_id)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            payload["feature_id"] = work_id
            payload["last_queue_offset"] = 0
        graph.update_state(config, payload)
        return
    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph

    graph = ensure_task_graph(work_id, root=root, feature_id=feature_id)
    config = thread_config(work_id)
    snapshot = graph.get_state(config)
    if not snapshot.values:
        payload.update(
            {
                "task_id": work_id,
                "feature_id": feature_id or "",
                "last_queue_offset": 0,
                "skill_playbooks": [],
            }
        )
    graph.update_state(config, payload)


def _invoke_role_turn(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
    model_id: str | None = None,
    resume: bool = False,
) -> None:
    if tier == "epic":
        from cascade.agent.graph_turn import clear_turn_model_override
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(work_id, root=root)
        config = thread_config(work_id)
        graph.invoke({}, config)
        if model_id is not None:
            clear_turn_model_override(graph, config)
        return
    if tier == "feature":
        from cascade.agent.graph_turn import clear_turn_model_override
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(work_id, root=root)
        config = thread_config(work_id)
        graph.invoke({}, config)
        if model_id is not None:
            clear_turn_model_override(graph, config)
        return
    from cascade.agent.graph_turn import clear_turn_model_override
    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph
    from cascade.task.failure import defer_task_teardown, flush_deferred_task_teardown

    graph = ensure_task_graph(work_id, root=root, feature_id=feature_id)
    config = thread_config(work_id)
    payload: dict = {}
    if model_id is not None:
        payload["model_id"] = model_id
    token = defer_task_teardown()
    try:
        graph.invoke(payload, config)
        if model_id is not None:
            clear_turn_model_override(graph, config)
    finally:
        flush_deferred_task_teardown(token)
