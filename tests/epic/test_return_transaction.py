"""Durable boundaries for the active-to-backlog mutation transaction."""

from __future__ import annotations

import pytest

from cascade.epic.return_transaction import (
    ActiveToBacklogFiles,
    ActiveToBacklogTransaction,
    TransitionStep,
    TransitionUnsafe,
    execute_file_transaction,
)


def _operations(calls: list[str]):
    return {
        "assert_safe": lambda: calls.append("safe"),
        "preserve_artifacts": lambda: calls.append("preserve"),
        "restore_source_brief": lambda: calls.append("restore"),
        "remove_active_pointer": lambda: calls.append("pointer"),
        "invalidate_stale_run": lambda: calls.append("invalidate"),
    }


def test_transaction_persists_every_durable_boundary_in_order(tmp_path) -> None:
    calls: list[str] = []
    transaction = ActiveToBacklogTransaction(root=tmp_path, epic_id="epic_030", request_id="one")

    result = transaction.execute(**_operations(calls))

    assert calls == ["safe", "preserve", "restore", "pointer", "invalidate"]
    assert result.completed_steps == tuple(TransitionStep)
    assert transaction.load() == result


def test_repeating_a_completed_request_does_not_repeat_mutations(tmp_path) -> None:
    calls: list[str] = []
    transaction = ActiveToBacklogTransaction(root=tmp_path, epic_id="epic_030", request_id="one")
    transaction.execute(**_operations(calls))

    result = transaction.execute(**_operations(calls))

    assert result.complete
    assert calls == ["safe", "preserve", "restore", "pointer", "invalidate"]


def test_unsafe_state_does_not_create_an_intent_marker(tmp_path) -> None:
    transaction = ActiveToBacklogTransaction(root=tmp_path, epic_id="epic_030", request_id="one")

    with pytest.raises(TransitionUnsafe):
        transaction.execute(
            assert_safe=lambda: (_ for _ in ()).throw(TransitionUnsafe("dirty git")),
            preserve_artifacts=lambda: None,
            restore_source_brief=lambda: None,
            remove_active_pointer=lambda: None,
            invalidate_stale_run=lambda: None,
        )

    assert transaction.load() is None


def test_an_incomplete_prior_intent_is_resumed_not_competed(tmp_path) -> None:
    first = ActiveToBacklogTransaction(root=tmp_path, epic_id="epic_030", request_id="one")
    calls: list[str] = []
    crashing = _operations(calls)
    crashing["restore_source_brief"] = lambda: (_ for _ in ()).throw(RuntimeError("crash"))

    with pytest.raises(RuntimeError):
        first.execute(**crashing)

    second = ActiveToBacklogTransaction(root=tmp_path, epic_id="epic_030", request_id="two")
    second.execute(**_operations(calls))

    assert first.load() is not None
    assert first.load().complete
    assert calls == ["safe", "preserve", "safe", "restore", "pointer", "invalidate"]


def test_file_transaction_refuses_operator_trunk_without_lifecycle_mutation(tmp_path) -> None:
    source = tmp_path / "active.md"
    source.write_text("source", encoding="utf-8")
    files = ActiveToBacklogFiles(
        source_brief=source,
        backlog_brief=tmp_path / "backlog.md",
        active_pointer=tmp_path / "pointer.md",
        preserved_artifact=tmp_path / "artifact.md",
        stale_run_marker=tmp_path / "stale",
    )

    with pytest.raises(TransitionUnsafe, match="operator trunk"):
        execute_file_transaction(root=tmp_path, epic_id="epic_030", request_id="one", files=files)

    assert not (tmp_path / ".cascade" / "epic-transitions").exists()
    assert not files.backlog_brief.exists()
