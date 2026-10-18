"""propose_epic_amendment (task_027)."""

from __future__ import annotations

from pathlib import Path

import pytest

import cascade.feature.amendments  # noqa: F401 — registers tool
from cascade.amendments import AmendmentStoreError, read_amendment, sidecar_paths
from cascade.board.store import pin_parent, read_doc, write_doc
from cascade.feature.amendments import propose_epic_amendment
from cascade.feature.guard import FeatureToolDenied
from cascade.feature.mint import mint_task
from cascade.feature.registry import clear_feature_tools, feature_tools
from cascade.feature.wiring import load_feature_tools
from cascade.war_room.toasts import events_to_toasts
from cascade.watchdog import read_events
from tests.support import EPIC_BODY, add_doc, make_repo


@pytest.fixture(autouse=True)
def _tools() -> None:
    clear_feature_tools()
    load_feature_tools()
    yield
    clear_feature_tools()


@pytest.fixture
def board(tmp_path: Path) -> dict[str, object]:
    root = make_repo(tmp_path)
    epic = add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    epic = read_doc("epic_001", root=root)
    epic.body = EPIC_BODY
    write_doc(epic, root=root)
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    pin_parent("feat_001", "epic_001", root=root)
    epic_path = read_doc("epic_001", root=root).meta.path
    return {"root": root, "epic_path": epic_path}


def test_propose_happy_path_sidecar_and_blocked(board: dict[str, object]) -> None:
    root = board["root"]
    epic_path = board["epic_path"]
    epic_before = (root / epic_path.relative_to(root)).read_text(encoding="utf-8")

    amd_id = propose_epic_amendment(
        epic_path.relative_to(root).as_posix(),
        "Cross-module constraints",
        "Feature-owned write paths only.",
        "Need tighter isolation.",
        feature_id="feat_001",
        root=root,
    )

    assert amd_id == "amd_001"
    diff_path, meta_path = sidecar_paths(
        "feat_001", "Cross-module constraints", root=root
    )
    assert diff_path.is_file()
    assert meta_path.is_file()
    record = read_amendment(amd_id, root=root)
    assert record.state == "pending"
    assert record.feature_id == "feat_001"
    assert record.epic_id == "epic_001"

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "blocked"
    assert feature.meta.path.parts[-2] == "2_active"

    epic_after = (root / epic_path.relative_to(root)).read_text(encoding="utf-8")
    assert epic_after == epic_before


def test_propose_emits_amendment_proposed_on_epic_queue(board: dict[str, object]) -> None:
    root = board["root"]
    amd_id = propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "New text.",
        "Because.",
        feature_id="feat_001",
        root=root,
    )
    events, _ = read_events("epic_001", 0, root=root)
    proposed = [e for e in events if e.type == "AmendmentProposed"]
    assert len(proposed) == 1
    assert proposed[0].dest == "epic_001"
    assert proposed[0].payload == {
        "feature_id": "feat_001",
        "epic_id": "epic_001",
        "section": "Cross-module constraints",
        "diff_path": read_amendment(amd_id, root=root).diff_path.as_posix(),
        "amd_id": amd_id,
    }


def test_propose_emits_war_room_amendment_toast(board: dict[str, object]) -> None:
    root = board["root"]
    propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "New text.",
        "Because.",
        feature_id="feat_001",
        root=root,
    )
    events, _ = read_events("war_room", 0, root=root)
    toasts = events_to_toasts(events)
    assert len(toasts) == 1
    assert toasts[0]["kind"] == "amendment"
    assert "Cross-module constraints" in toasts[0]["body"]
    assert toasts[0]["link"] == "/api/doc/epic_001"


def test_propose_conflict_on_second_same_section(board: dict[str, object]) -> None:
    root = board["root"]
    propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "First proposal.",
        "First.",
        feature_id="feat_001",
        root=root,
    )
    add_doc(
        root,
        id="feat_002",
        title="Other feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    pin_parent("feat_002", "epic_001", root=root)
    with pytest.raises(AmendmentStoreError, match=r"open amendment amd_001"):
        propose_epic_amendment(
            "epic_001",
            "Cross-module constraints",
            "Second proposal.",
            "Second.",
            feature_id="feat_002",
            root=root,
        )


def test_mint_task_refused_while_blocked(board: dict[str, object]) -> None:
    root = board["root"]
    propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "New text.",
        "Because.",
        feature_id="feat_001",
        root=root,
    )
    with pytest.raises(FeatureToolDenied, match="blocked awaiting amendment"):
        mint_task("Should not mint", feature_id="feat_001", root=root)


def test_mint_blocked_message_distinct_from_comment(board: dict[str, object]) -> None:
    root = board["root"]
    propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "New text.",
        "Because.",
        feature_id="feat_001",
        root=root,
    )
    with pytest.raises(FeatureToolDenied) as exc_info:
        mint_task("No", feature_id="feat_001", root=root)
    message = str(exc_info.value)
    assert "blocked awaiting amendment" in message
    assert "blocking human comment" not in message


def test_propose_does_not_mutate_epic_git_history(board: dict[str, object]) -> None:
    root = board["root"]
    epic = read_doc("epic_001", root=root)
    rel = epic.meta.path.relative_to(root).as_posix()
    import subprocess

    before = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", rel],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "New text.",
        "Because.",
        feature_id="feat_001",
        root=root,
    )

    after = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", rel],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert after == before


def test_propose_after_reject_on_same_section(board: dict[str, object]) -> None:
    from cascade.epic.amendments import resolve_amendment

    root = board["root"]
    amd_id = propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "First proposal.",
        "First.",
        feature_id="feat_001",
        root=root,
    )
    resolve_amendment(amd_id, "reject", epic_id="epic_001", root=root)
    assert read_doc("feat_001", root=root).meta.status == "active"

    amd_id_2 = propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "Second proposal.",
        "Second.",
        feature_id="feat_001",
        root=root,
    )
    assert amd_id_2 == "amd_002"
    assert read_amendment(amd_id_2, root=root).state == "pending"


def test_mint_task_succeeds_after_reject_unblocks(board: dict[str, object]) -> None:
    from cascade.epic.amendments import resolve_amendment

    root = board["root"]
    amd_id = propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "New text.",
        "Because.",
        feature_id="feat_001",
        root=root,
    )
    resolve_amendment(amd_id, "reject", epic_id="epic_001", root=root)
    task_id = mint_task("Post-reject task", feature_id="feat_001", root=root)
    assert task_id.startswith("task_")


def test_propose_rejects_wrong_basename_only_path(board: dict[str, object]) -> None:
    root = board["root"]
    epic_path = board["epic_path"]
    decoy = root / "scratch" / epic_path.name
    decoy.parent.mkdir(parents=True, exist_ok=True)
    decoy.write_text("# decoy\n", encoding="utf-8")
    with pytest.raises(FeatureToolDenied, match="does not resolve"):
        propose_epic_amendment(
            decoy.name,
            "Cross-module constraints",
            "Nope.",
            "Because.",
            feature_id="feat_001",
            root=root,
        )


def test_registry_points_at_real_propose() -> None:
    import cascade.feature.amendments as amendments_mod

    tools = feature_tools()
    assert tools["propose_epic_amendment"] is amendments_mod.propose_epic_amendment
