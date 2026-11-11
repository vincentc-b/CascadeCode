"""Durable semantic review-thread anchors and read-time freshness."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cascade.comments import read_comments, resolve_comment
from cascade.workspace import (
    C4ReviewPayload,
    C4ReviewSide,
    C4ReviewTarget,
    C4ReviewView,
    WorkspaceError,
    build_semantic_thread_anchor,
    create_semantic_thread,
    read_semantic_threads,
)
from tests.support import add_doc, make_repo


REVISION_A = "a" * 40
REVISION_B = "b" * 40


@pytest.fixture
def review_repo(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_034", title="Architecture", tier="epic", status="active")
    add_doc(
        root,
        id="feat_034_004",
        title="Paired review",
        tier="feature",
        status="active",
        parent="epic_034",
    )
    return root


def test_all_anchor_types_round_trip_separately_from_heading_anchors(
    review_repo: Path,
) -> None:
    payload = _payload()
    requests = (
        ("requirement", "REQ-7", "current", None),
        ("view", "context", "current", "systemContextViews"),
        ("element", "element.system", "proposed", None),
        ("relationship", "relationship.calls", "proposed", None),
    )
    ids = []
    for kind, key, side, level in requests:
        anchor = build_semantic_thread_anchor(
            payload, kind=kind, target_key=key, source_side=side, level=level
        )
        ids.append(
            create_semantic_thread(
                payload,
                anchor,
                f"review {kind}",
                False,
                owner="feature-team",
                author="human",
                root=review_repo,
            )
        )

    threads = read_semantic_threads(payload, owner="feature-team", root=review_repo)
    assert [thread.id for thread in threads] == ids
    assert [thread.anchor.kind for thread in threads] == [row[0] for row in requests]
    assert all(thread.freshness == "current" for thread in threads)
    assert threads[1].anchor.view_key == "context"
    assert threads[1].anchor.level == "systemContextViews"
    assert threads[0].anchor.source_path is None  # legacy narrow payload remains readable
    assert threads[2].anchor.original_source_reference == "proposed-context.svg"
    stored = read_comments("feat_034_004", root=review_repo)
    assert all(row.anchor is None and row.section == "semantic-review" for row in stored)
    assert all(row.semantic_anchor is not None for row in stored)


def test_exact_cross_repository_revision_is_validated(review_repo: Path) -> None:
    payload = _payload()
    anchor = build_semantic_thread_anchor(
        payload,
        kind="element",
        target_key="element.system",
        source_side="proposed",
    )
    assert anchor.repository_key == "docs-proposed"
    assert anchor.revision == REVISION_B

    with pytest.raises(WorkspaceError, match="repository revision"):
        create_semantic_thread(
            payload,
            replace(anchor, repository_key="docs-current", revision=REVISION_A),
            "wrong repository",
            False,
            owner="feature-team",
            author="human",
            root=review_repo,
        )
    with pytest.raises(WorkspaceError, match="owner scope"):
        create_semantic_thread(
            payload,
            anchor,
            "wrong owner",
            False,
            owner="another-team",
            author="human",
            root=review_repo,
        )


def test_outdated_target_retains_original_links_and_blocking_until_human_resolution(
    review_repo: Path,
) -> None:
    original = _payload()
    anchor = build_semantic_thread_anchor(
        original,
        kind="relationship",
        target_key="relationship.calls",
        source_side="proposed",
    )
    thread_id = create_semantic_thread(
        original,
        anchor,
        "This relationship must be addressed",
        True,
        owner="feature-team",
        author="human",
        root=review_repo,
    )
    removed = replace(
        original,
        review_unit_id="architecture-review-next",
        reviewed_tuple_digest="next",
        views=(replace(original.views[0], proposed=replace(
            original.views[0].proposed,
            targets=(C4ReviewTarget("element", "element.system"),),
        )),),
    )

    thread = read_semantic_threads(
        removed, owner="feature-team", root=review_repo
    )[0]
    assert thread.freshness == "outdated"
    assert thread.outdated_reason == "target_missing_or_renamed"
    assert thread.state == "open"
    assert thread.blocking is True
    assert thread.anchor.target_key == "relationship.calls"
    assert thread.anchor.original_source_reference == "proposed-context.svg"
    assert thread.anchor.original_diff_link == "git:model-a..model-b"

    resolve_comment(
        "feat_034_004", thread_id, author="human", root=review_repo
    )
    resolved = read_semantic_threads(
        removed, owner="feature-team", root=review_repo
    )[0]
    assert resolved.freshness == "outdated"
    assert resolved.state == "resolved"
    assert resolved.blocking is True


def test_revision_drift_is_outdated_even_when_target_still_exists(review_repo: Path) -> None:
    original = _payload()
    anchor = build_semantic_thread_anchor(
        original, kind="view", target_key="context", source_side="current",
        level="systemContextViews",
    )
    create_semantic_thread(
        original, anchor, "pin this", False, owner="feature-team", author="human",
        root=review_repo,
    )
    drifted_side = replace(original.views[0].current, revision="c" * 40)
    drifted = replace(
        original,
        repositories=(
            {"side": "current", "repository_key": "docs-current", "revision": "c" * 40},
            original.repositories[1],
        ),
        views=(replace(original.views[0], current=drifted_side),),
    )

    thread = read_semantic_threads(
        drifted, owner="feature-team", root=review_repo
    )[0]
    assert thread.freshness == "outdated"
    assert thread.outdated_reason == "revision_mismatch"


def _payload() -> C4ReviewPayload:
    current = C4ReviewSide(
        "docs-current",
        REVISION_A,
        "current-context.svg",
        (
            C4ReviewTarget("element", "element.system"),
            C4ReviewTarget("relationship", "relationship.calls"),
        ),
    )
    proposed = C4ReviewSide(
        "docs-proposed",
        REVISION_B,
        "proposed-context.svg",
        (
            C4ReviewTarget("element", "element.system"),
            C4ReviewTarget("relationship", "relationship.calls"),
        ),
    )
    return C4ReviewPayload(
        state="ready",
        owner_work_id="feat_034_004",
        authorized_owner="feature-team",
        review_unit_id="architecture-review-exact",
        reviewed_tuple_digest="exact",
        repositories=(
            {"side": "current", "repository_key": "docs-current", "revision": REVISION_A},
            {"side": "proposed", "repository_key": "docs-proposed", "revision": REVISION_B},
        ),
        views=(C4ReviewView(
            "context", "systemContextViews", "changed", current, proposed
        ),),
        changed_views=(("context", "systemContextViews"),),
        legend=(),
        summary="changed",
        requirements=("REQ-7",),
        decisions=("ADR-4",),
        diffs={
            "source": "git:model-a..model-b",
            "plan": "git:plan-a..plan-b",
            "model": {"identities": []},
        },
    )
