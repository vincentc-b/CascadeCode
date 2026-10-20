"""Table-driven cases for blocking_threads_for and is_section_thread (feat_019 task_084)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cascade.board.store import read_doc, write_doc
from cascade.comments.gate import blocking_threads_for, is_section_thread
from cascade.comments.store import comment
from tests.support import EPIC_BODY, add_doc, make_repo


def _set_cites(root: Path, feature_id: str, cites: list[str]) -> None:
    doc = read_doc(feature_id, root=root)
    doc.meta.cites = cites
    write_doc(doc, root=root)


def _gate_board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(
        root,
        id="epic_002",
        title="Plan threads",
        tier="epic",
        status="active",
        children=["feat_001", "feat_002"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Citing feature",
        tier="feature",
        status="active",
        parent="epic_002",
        children=["task_001"],
    )
    add_doc(
        root,
        id="feat_002",
        title="Other feature",
        tier="feature",
        status="active",
        parent="epic_002",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="backlog",
        parent="feat_001",
    )
    _set_cites(root, "feat_001", ["epic_002#cross-module-constraints"])
    return root


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            {
                "name": "blocks_list",
                "setup": lambda root: comment(
                    "feat_001",
                    "scope",
                    "blocks task only via explicit blocks list",
                    author="human",
                    blocking=True,
                    blocks=["task_001"],
                    root=root,
                ),
                "query": "task_001",
                "blocked": True,
                "thread_doc": "feat_001",
                "warn": False,
            },
            id="a_blocks_list",
        ),
        pytest.param(
            {
                "name": "epic_section_citing_feature",
                "setup": lambda root: comment(
                    "epic_002",
                    "cross-module-constraints",
                    "epic section hold",
                    author="human",
                    blocking=True,
                    root=root,
                ),
                "query": "feat_001",
                "blocked": True,
                "thread_doc": "epic_002",
                "warn": False,
            },
            id="b_epic_section_citing_feature",
        ),
        pytest.param(
            {
                "name": "feature_doc_level_child_task",
                "setup": lambda root: comment(
                    "feat_001",
                    "scope",
                    "feature-wide",
                    author="human",
                    blocking=True,
                    root=root,
                ),
                "query": "task_001",
                "blocked": True,
                "thread_doc": "feat_001",
                "warn": False,
            },
            id="c_feature_doc_level_blocks_task",
        ),
        pytest.param(
            {
                "name": "task_inherits_feature_scope",
                "setup": lambda root: comment(
                    "feat_001",
                    "api-contracts",
                    "section on feature is still doc+children",
                    author="human",
                    blocking=True,
                    root=root,
                ),
                "query": "task_001",
                "blocked": True,
                "thread_doc": "feat_001",
                "warn": False,
            },
            id="task_inherit_parent_feature",
        ),
        pytest.param(
            {
                "name": "ancestor_epic_section_on_task",
                "setup": lambda root: comment(
                    "epic_002",
                    "cross-module-constraints",
                    "from epic ancestor",
                    author="human",
                    blocking=True,
                    root=root,
                ),
                "query": "task_001",
                "blocked": True,
                "thread_doc": "epic_002",
                "warn": False,
            },
            id="ancestor_epic_section_hits_citing_task",
        ),
        pytest.param(
            {
                "name": "non_citing_feature_clear",
                "setup": lambda root: comment(
                    "epic_002",
                    "cross-module-constraints",
                    "should not hit feat_002",
                    author="human",
                    blocking=True,
                    root=root,
                ),
                "query": "feat_002",
                "blocked": False,
                "thread_doc": None,
                "warn": False,
            },
            id="non_citing_feature_not_blocked",
        ),
        pytest.param(
            {
                "name": "unmatched_cite_warning",
                "setup": lambda root: (
                    _set_cites(root, "feat_002", ["epic_002#renamed-away"]),
                    None,
                )[1],
                "query": "feat_002",
                "blocked": False,
                "thread_doc": None,
                "warn": True,
            },
            id="unmatched_cite_warning",
        ),
        pytest.param(
            {
                "name": "historical_free_text_doc_level",
                "setup": lambda root: comment(
                    "feat_001",
                    "Open questions",
                    "legacy section label",
                    author="human",
                    blocking=True,
                    root=root,
                ),
                "query": "task_001",
                "blocked": True,
                "thread_doc": "feat_001",
                "warn": False,
            },
            id="historical_free_text_as_doc_level",
        ),
    ],
)
def test_blocking_threads_for_table(tmp_path: Path, case: dict) -> None:
    root = _gate_board(tmp_path)
    case["setup"](root)
    result = blocking_threads_for(case["query"], root=root)
    assert result.blocked is case["blocked"]
    if case["thread_doc"]:
        assert len(result.threads) == 1
        assert result.threads[0].doc_id == case["thread_doc"]
        assert result.threads[0].blocking is True
    else:
        assert result.threads == []
    if case["warn"]:
        assert any("unmatched cite" in w for w in result.warnings)
    else:
        assert not any("unmatched cite" in w for w in result.warnings)


def test_is_section_thread_heading_match(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_002", title="Epic", tier="epic", status="active")
    doc = read_doc("epic_002", root=root)
    write_doc(replace(doc, body=EPIC_BODY), root=root)
    assert is_section_thread("epic_002", "cross-module-constraints", root=root)
    assert not is_section_thread("epic_002", "Open questions", root=root)
    assert not is_section_thread("epic_002", "general", root=root)
