"""Dispatch law: principal, dependencies, cap, and skills."""

from pathlib import Path

import pytest

from cascade.board import move_doc, read_doc, write_doc
from cascade.watchdog import (
    activate_epic,
    dispatch_feature,
    dispatch_task,
    read_events,
    register_boot_hook,
    register_teardown_hook,
    watchdog_tick,
)
from tests.support import add_doc, make_repo


def _activate_epic(root: Path, epic_id: str = "epic_001") -> None:
    from cascade.workspace.integration_worktree import get_integration_worktree

    if get_integration_worktree(root, "epic", epic_id) is not None:
        return
    assert activate_epic(epic_id, "human", root=root).ok


def _open_feature(root: Path, feat_id: str = "feat_001", *, epic_id: str = "epic_001") -> None:
    _activate_epic(root, epic_id)
    assert dispatch_feature(feat_id, "human", root=root).ok


def test_activate_epic_human_succeeds_and_boss_is_unauthorized(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Ready epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="epic_002", title="Boss epic", tier="epic", status="ready_to_plan")
    booted: list[str] = []
    register_boot_hook("epic", booted.append)

    result = activate_epic("epic_001", "human", root=root)
    assert result.ok is True
    assert result.reason is None
    assert result.event is not None
    assert result.event.type == "EpicActivated"
    assert result.event.payload["epic_id"] == "epic_001"
    assert result.event.payload["by"] == "human"
    assert result.event.dest == "epic_001"
    assert booted == ["epic_001"]
    activated = read_doc("epic_001", root=root)
    assert activated.meta.status == "active"
    assert activated.meta.path.parent.name == "2_active"

    refused = activate_epic("epic_002", "boss", root=root)
    assert refused.ok is False
    assert refused.reason == "unauthorized"
    assert refused.event is None
    assert booted == ["epic_001"]
    untouched = read_doc("epic_002", root=root)
    assert untouched.meta.status == "ready_to_plan"
    assert untouched.meta.path.parent.name == "1_backlog"
    queued, _offset = read_events("epic_002", 0, root=root)
    assert queued == []

    missing = activate_epic("epic_999", "human", root=root)
    assert missing.reason == "not_found"
    assert missing.event is None


def test_boot_hook_failure_keeps_move_and_event(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Hook epic", tier="epic")

    def boom(_work_id: str) -> None:
        raise RuntimeError("hook failed")

    register_boot_hook("epic", boom)
    with pytest.raises(RuntimeError, match="hook failed"):
        activate_epic("epic_001", "human", root=root)

    doc = read_doc("epic_001", root=root)
    assert doc.meta.status == "active"
    events, _offset = read_events("epic_001", 0, root=root)
    assert [event.type for event in events] == ["EpicActivated"]
    watchdog_tick(root)
    assert read_doc("epic_001", root=root).meta.status == "active"


def test_dispatch_feature_by_human_and_boss_and_unmet_deps(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    _activate_epic(root)
    booted: list[str] = []
    register_boot_hook("feature", booted.append)
    add_doc(root, id="feat_001", title="Human feature", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Boss feature", tier="feature", parent="epic_001")
    add_doc(root, id="feat_004", title="Unfinished dep", tier="feature", parent="epic_001")
    add_doc(
        root,
        id="feat_003",
        title="Waiting feature",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_004"],
    )

    human = dispatch_feature("feat_001", "human", root=root)
    boss = dispatch_feature("feat_002", "boss", root=root)
    assert human.ok and human.event is not None
    assert boss.ok and boss.event is not None
    assert human.event.type == "FeatureReadyToPlan"
    assert human.event.payload["by"] == "human"
    assert human.event.payload["feature_id"] == "feat_001"
    assert boss.event.payload["by"] == "boss"
    assert boss.event.payload["id"] == "feat_002"
    assert read_doc("feat_001", root=root).meta.status == "active"
    assert read_doc("feat_002", root=root).meta.path.parent.name == "2_active"
    assert booted == ["feat_001", "feat_002"]

    refused = dispatch_feature("feat_003", "human", root=root)
    assert refused.ok is False
    assert refused.reason == "unmet_deps"
    assert refused.event is None
    waiting = read_doc("feat_003", root=root)
    assert waiting.meta.status == "backlog"
    assert waiting.meta.path.parent.name == "1_backlog"
    queued, _offset = read_events("feat_003", 0, root=root)
    assert queued == []


def test_dispatch_task_emits_and_boots(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _open_feature(root)
    booted: list[str] = []
    torn: list[str] = []

    def _boot(work_id: str) -> None:
        booted.append(work_id)
        watchdog_tick(root)

    register_boot_hook("task", _boot)
    register_teardown_hook("task", torn.append)

    result = dispatch_task("task_001", "human", root=root)
    assert result.ok is True
    assert result.reason is None
    assert result.event is not None
    assert result.event.type == "TaskDispatched"
    assert result.event.payload["id"] == "task_001"
    assert result.event.payload["task_id"] == "task_001"
    assert result.event.payload["feature_id"] == "feat_001"
    assert result.event.payload["by"] == "human"
    assert result.event.payload["skills"] == []
    assert booted == ["task_001"]
    assert torn == []
    assert read_doc("task_001", root=root).meta.status == "active"
    saved, _offset = read_events("task_001", 0, root=root)
    assert [event.type for event in saved] == ["TaskDispatched"]


def test_parallelism_cap_ignores_blocked_and_does_not_emit(tmp_path: Path) -> None:
    root = make_repo(tmp_path, parallelism=2)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task A", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Task B", tier="task", parent="feat_001")
    add_doc(root, id="task_003", title="Task C", tier="task", parent="feat_001")
    _open_feature(root)
    booted: list[str] = []
    register_boot_hook("task", booted.append)

    assert dispatch_task("task_001", "human", root=root).ok
    assert dispatch_task("task_002", "boss", root=root).ok
    capped = dispatch_task("task_003", "human", root=root)
    assert capped.ok is False
    assert capped.reason == "cap"
    assert capped.event is None
    waiting = read_doc("task_003", root=root)
    assert waiting.meta.status == "backlog"
    assert waiting.meta.path.parent.name == "1_backlog"
    queued, _offset = read_events("task_003", 0, root=root)
    assert queued == []
    war, _war_offset = read_events("war_room", 0, root=root)
    assert all(event.type not in {"TaskDispatched", "TaskDispatchQueued"} for event in war)
    assert booted == ["task_001", "task_002"]

    blocked = read_doc("task_001", root=root)
    blocked.meta.status = "blocked"
    write_doc(blocked, root=root)
    assert read_doc("task_001", root=root).meta.status == "blocked"
    assert read_doc("task_001", root=root).meta.path.parent.name == "2_active"
    watchdog_tick(root)
    assert read_doc("task_001", root=root).meta.status == "blocked"
    assert read_doc("task_002", root=root).meta.status == "active"

    started = dispatch_task("task_003", "human", root=root)
    assert started.ok is True
    assert started.event is not None
    assert started.event.type == "TaskDispatched"
    assert read_doc("task_003", root=root).meta.status == "active"
    assert booted == ["task_001", "task_002", "task_003"]
    saved, _saved_offset = read_events("task_003", 0, root=root)
    assert [event.type for event in saved] == ["TaskDispatched"]


def test_skills_override_and_rejected_paths(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Skilled task", tier="task", parent="feat_001")
    add_doc(
        root,
        id="task_002",
        title="Clear skills",
        tier="task",
        parent="feat_001",
        skills=[Path("skills/old/SKILL.md")],
    )
    _open_feature(root)
    skill = root / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# demo\n", encoding="utf-8")

    missing = dispatch_task("task_001", "human", skills=[Path("skills/missing/SKILL.md")], root=root)
    assert missing.reason == "bad_state"
    assert missing.event is None
    assert read_doc("task_001", root=root).meta.path.parent.name == "1_backlog"
    assert read_doc("task_001", root=root).meta.skills == []

    escaped = dispatch_task("task_001", "boss", skills=[Path("../SKILL.md")], root=root)
    assert escaped.reason == "bad_state"
    assert escaped.event is None
    assert read_doc("task_001", root=root).meta.status == "backlog"

    absolute = dispatch_task("task_001", "human", skills=[skill.resolve()], root=root)
    assert absolute.reason == "bad_state"
    assert read_doc("task_001", root=root).meta.path.parent.name == "1_backlog"

    accepted = dispatch_task(
        "task_001",
        "human",
        skills=[Path("skills/demo/SKILL.md")],
        root=root,
    )
    assert accepted.ok is True
    assert accepted.event is not None
    assert accepted.event.payload["skills"] == ["skills/demo/SKILL.md"]
    updated = read_doc("task_001", root=root)
    assert [path.as_posix() for path in updated.meta.skills] == ["skills/demo/SKILL.md"]
    assert "skills/demo/SKILL.md" in updated.body
    assert updated.meta.status == "active"

    cleared = dispatch_task("task_002", "boss", skills=[], root=root)
    assert cleared.ok is True
    assert cleared.event is not None
    assert cleared.event.payload["skills"] == []
    assert read_doc("task_002", root=root).meta.skills == []


def test_depends_on_existing_but_not_completed(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Dependency", tier="task", parent="feat_001")
    _open_feature(root)
    add_doc(
        root,
        id="task_002",
        title="Blocked on dep",
        tier="task",
        parent="feat_001",
        depends_on=["task_001"],
    )
    refused = dispatch_task("task_002", "boss", root=root)
    assert refused.ok is False
    assert refused.reason == "unmet_deps"
    assert refused.event is None
    waiting = read_doc("task_002", root=root)
    assert waiting.meta.status == "backlog"
    assert waiting.meta.path.parent.name == "1_backlog"

    move_doc("task_001", "completed", root=root)
    assert read_doc("task_001", root=root).meta.status == "completed"
    assert read_doc("task_001", root=root).meta.path.parent.name == "3_completed"
    started = dispatch_task("task_002", "human", root=root)
    assert started.ok is True
    assert started.event is not None
    assert started.event.type == "TaskDispatched"
    assert read_doc("task_002", root=root).meta.status == "active"


def test_blocked_task_redispatch_and_cap(tmp_path: Path) -> None:
    root = make_repo(tmp_path, parallelism=1)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Restart me", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Holds the slot", tier="task", parent="feat_001")
    _open_feature(root)
    booted: list[str] = []
    register_boot_hook("task", booted.append)

    assert dispatch_task("task_001", "human", root=root).ok
    blocked = read_doc("task_001", root=root)
    blocked.meta.status = "blocked"
    write_doc(blocked, root=root)

    restarted = dispatch_task("task_001", "boss", root=root)
    assert restarted.ok is True
    assert restarted.event is not None
    assert restarted.event.type == "TaskDispatched"
    again = read_doc("task_001", root=root)
    assert again.meta.status == "active"
    assert again.meta.path.parent.name == "2_active"
    assert booted == ["task_001", "task_001"]
    queued, _offset = read_events("task_001", 0, root=root)
    assert [event.type for event in queued] == ["TaskDispatched", "TaskDispatched"]

    held = read_doc("task_001", root=root)
    held.meta.status = "blocked"
    write_doc(held, root=root)
    assert dispatch_task("task_002", "human", root=root).ok
    refused = dispatch_task("task_001", "human", root=root)
    assert refused.ok is False
    assert refused.reason == "cap"
    assert refused.event is None
    stayed = read_doc("task_001", root=root)
    assert stayed.meta.status == "blocked"
    assert stayed.meta.path.parent.name == "2_active"
    assert booted == ["task_001", "task_001", "task_002"]


def test_second_dispatch_of_active_task_is_bad_state(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Already running", tier="task", parent="feat_001")
    _open_feature(root)
    booted: list[str] = []
    register_boot_hook("task", booted.append)
    assert dispatch_task("task_001", "human", root=root).ok
    again = dispatch_task("task_001", "boss", root=root)
    assert again.ok is False
    assert again.reason == "bad_state"
    assert again.event is None
    assert read_doc("task_001", root=root).meta.status == "active"
    queued, _offset = read_events("task_001", 0, root=root)
    assert [event.type for event in queued] == ["TaskDispatched"]
    assert booted == ["task_001"]


def test_unmet_deps_when_dependency_is_active_or_blocked(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="First epic", tier="epic")
    add_doc(
        root,
        id="epic_002",
        title="Needs the first",
        tier="epic",
        depends_on=["epic_001"],
    )
    waiting = activate_epic("epic_002", "human", root=root)
    assert waiting.reason == "unmet_deps"
    assert read_doc("epic_002", root=root).meta.status == "backlog"

    assert activate_epic("epic_001", "human", root=root).ok
    still = activate_epic("epic_002", "human", root=root)
    assert still.reason == "unmet_deps"
    assert still.event is None
    assert read_doc("epic_002", root=root).meta.path.parent.name == "1_backlog"

    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Dependency", tier="task", parent="feat_001")
    add_doc(
        root,
        id="task_002",
        title="Needs task one",
        tier="task",
        parent="feat_001",
        depends_on=["task_001"],
    )
    _open_feature(root)
    assert dispatch_task("task_001", "human", root=root).ok
    active_dep = dispatch_task("task_002", "boss", root=root)
    assert active_dep.reason == "unmet_deps"
    assert read_doc("task_002", root=root).meta.status == "backlog"

    blocked = read_doc("task_001", root=root)
    blocked.meta.status = "blocked"
    write_doc(blocked, root=root)
    blocked_dep = dispatch_task("task_002", "human", root=root)
    assert blocked_dep.reason == "unmet_deps"
    assert blocked_dep.event is None
    assert read_doc("task_002", root=root).meta.path.parent.name == "1_backlog"


def test_cap_does_not_rewrite_illegal_skills(tmp_path: Path) -> None:
    root = make_repo(tmp_path, parallelism=1)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Running", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Waiting", tier="task", parent="feat_001")
    _open_feature(root)
    assert dispatch_task("task_001", "human", root=root).ok
    refused = dispatch_task(
        "task_002",
        "boss",
        skills=[Path("skills/missing/SKILL.md")],
        root=root,
    )
    assert refused.reason == "cap"
    assert refused.event is None
    waiting = read_doc("task_002", root=root)
    assert waiting.meta.skills == []
    assert waiting.meta.status == "backlog"
    assert waiting.meta.path.parent.name == "1_backlog"


def test_missing_stored_skill_refuses_without_moving(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(
        root,
        id="task_001",
        title="Broken skill",
        tier="task",
        parent="feat_001",
        skills=[Path("skills/missing/SKILL.md")],
    )
    refused = dispatch_task("task_001", "human", root=root)
    assert refused.reason == "bad_state"
    assert refused.event is None
    doc = read_doc("task_001", root=root)
    assert [path.as_posix() for path in doc.meta.skills] == ["skills/missing/SKILL.md"]
    assert doc.meta.status == "backlog"
    assert doc.meta.path.parent.name == "1_backlog"


def test_dispatch_feature_and_task_refuse_unknown_principal(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")

    feature = dispatch_feature("feat_001", "planner", root=root)  # type: ignore[arg-type]
    assert feature.ok is False
    assert feature.reason == "unauthorized"
    assert feature.event is None
    assert read_doc("feat_001", root=root).meta.path.parent.name == "1_backlog"

    task = dispatch_task("task_001", "planner", root=root)  # type: ignore[arg-type]
    assert task.ok is False
    assert task.reason == "unauthorized"
    assert task.event is None
    assert read_doc("task_001", root=root).meta.path.parent.name == "1_backlog"


def test_symlink_skill_outside_repo_is_bad_state(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Linked skill", tier="task", parent="feat_001")
    outside = tmp_path / "outside_skill.md"
    outside.write_text("# outside\n", encoding="utf-8")
    link = root / "skills" / "escape.md"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)
    refused = dispatch_task("task_001", "human", skills=[Path("skills/escape.md")], root=root)
    assert refused.reason == "bad_state"
    assert refused.event is None
    doc = read_doc("task_001", root=root)
    assert doc.meta.skills == []
    assert doc.meta.status == "backlog"
    assert doc.meta.path.parent.name == "1_backlog"
