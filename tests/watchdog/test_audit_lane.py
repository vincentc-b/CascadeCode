from __future__ import annotations

import errno
import json
import multiprocessing
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import cascade.board.store as board_store
import cascade.watchdog.audit_lane as audit_lane_module
from cascade.watchdog.audit_lane import (
    AuditPassTimedOut,
    AuditPassResult,
    HealthAuditLane,
    _WorkspaceClaim,
    _run_bounded_audit_pass_inline,
    audit_failure_path,
    audit_receipt_path,
    canonical_audit_root,
    read_audit_failure,
    read_audit_receipt,
    run_bounded_audit_pass,
)
from cascade.watchdog.config import HealthAuditConfig, read_health_audit_config
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, make_repo


class Clock:
    def __init__(
        self, *, monotonic: float = 100.0, utc: datetime | None = None
    ) -> None:
        self.monotonic = monotonic
        self.utc = utc or datetime(2026, 11, 8, tzinfo=timezone.utc)

    def tick(self, seconds: float) -> None:
        self.monotonic += seconds
        self.utc += timedelta(seconds=seconds)


def _process_gone_or_zombie(pid: int) -> bool:
    status = Path(f"/proc/{pid}/status")
    try:
        return not status.exists() or "State:\tZ" in status.read_text(encoding="utf-8")
    except (FileNotFoundError, ProcessLookupError):
        return True


def _lane(
    root: Path,
    clock: Clock,
    run_pass,
    *,
    interval: int = 60,
    jitter=lambda _low, high: high,
) -> HealthAuditLane:
    return HealthAuditLane(
        root=root,
        config=HealthAuditConfig(enabled=True, interval_seconds=interval),
        run_pass=run_pass,
        monotonic=lambda: clock.monotonic,
        utc_now=lambda: clock.utc,
        jitter=jitter,
    )


def test_completed_pass_persists_compact_receipt_and_bounded_jitter(
    tmp_path: Path,
) -> None:
    clock = Clock()

    def run(cursor: str | None, _cancel: threading.Event) -> AuditPassResult:
        assert cursor is None
        clock.tick(2.5)
        return AuditPassResult(next_cursor="tier:feature", counts={"observed": 3})

    lane = _lane(tmp_path, clock, run, interval=100)
    assert lane.run_due_pass() is True

    receipt = read_audit_receipt(tmp_path)
    assert receipt == {
        "last_completed_at": "2026-11-08T00:00:02.500000+00:00",
        "next_scheduled_at": "2026-11-08T00:01:47.500000+00:00",
        "interval_seconds": 100,
        "duration_seconds": 2.5,
        "counts": {"observed": 3},
        "next_cursor": "tier:feature",
    }
    assert lane.deadline == pytest.approx(207.5)
    assert audit_receipt_path(tmp_path).is_relative_to(tmp_path / ".cascade")


@pytest.mark.parametrize("runtime_path", [audit_receipt_path, audit_failure_path])
def test_nonregular_runtime_state_cannot_block_or_be_replaced(
    tmp_path: Path, runtime_path
) -> None:
    path = runtime_path(tmp_path)
    path.parent.mkdir(parents=True)
    os.mkfifo(path)
    clock = Clock()
    calls = 0

    def run(*_args) -> AuditPassResult:
        nonlocal calls
        calls += 1
        return AuditPassResult(next_cursor="done", counts={"healthy": 1})

    if runtime_path is audit_receipt_path:
        with pytest.raises(OSError, match="not a regular file"):
            _lane(tmp_path, clock, run)
    else:
        lane = _lane(tmp_path, clock, run)
        with pytest.raises(OSError, match="not a regular file"):
            lane.run_due_pass()
        assert calls == 0
        with _WorkspaceClaim(tmp_path):
            pass
        assert path.is_fifo()


def test_timed_out_candidate_evidence_survives_other_pages_and_restart(
    tmp_path: Path,
) -> None:
    clock = Clock()
    results = iter(
        (
            AuditPassResult(
                next_cursor="after:task_001",
                counts={"observed": 0, "unavailable_evidence": 1},
                timed_out_candidates=("task_001",),
            ),
            AuditPassResult(
                next_cursor="after:feat_001",
                counts={"healthy": 1},
                reassessed_candidates=("feat_001",),
            ),
            AuditPassResult(
                next_cursor="after:task_002",
                counts={"unavailable_evidence": 1},
                timed_out_candidates=("task_002",),
            ),
            AuditPassResult(
                next_cursor="after:task_001-unavailable",
                counts={"unavailable_evidence": 1},
            ),
            AuditPassResult(
                next_cursor="after:task_001-again",
                counts={"healthy": 1},
                reassessed_candidates=("task_001",),
            ),
            AuditPassResult(
                next_cursor="after:task_002-again",
                counts={"healthy": 1},
                reassessed_candidates=("task_002",),
            ),
        )
    )
    cursors: list[str | None] = []

    def run(cursor: str | None, _cancel: threading.Event) -> AuditPassResult:
        cursors.append(cursor)
        return next(results)

    lane = _lane(tmp_path, clock, run)
    assert lane.run_due_pass() is True
    assert read_audit_receipt(tmp_path)["next_cursor"] == "after:task_001"
    evidence = read_audit_failure(tmp_path)
    assert evidence is not None
    assert evidence["code"] == "candidate_observation_timeout"
    assert evidence["work_ids"] == ["task_001"]
    assert "retry" in evidence["next_action"]

    clock.tick(lane.deadline - clock.monotonic)
    assert lane.run_due_pass() is True
    assert read_audit_failure(tmp_path)["work_ids"] == ["task_001"]

    lane = _lane(tmp_path, clock, run)
    clock.tick(lane.deadline - clock.monotonic)
    assert lane.run_due_pass() is True
    assert read_audit_failure(tmp_path)["work_ids"] == ["task_001", "task_002"]

    clock.tick(lane.deadline - clock.monotonic)
    assert lane.run_due_pass() is True
    assert read_audit_failure(tmp_path)["work_ids"] == ["task_001", "task_002"]

    clock.tick(lane.deadline - clock.monotonic)
    assert lane.run_due_pass() is True
    assert read_audit_failure(tmp_path)["work_ids"] == ["task_002"]

    clock.tick(lane.deadline - clock.monotonic)
    assert lane.run_due_pass() is True
    assert read_audit_failure(tmp_path) is None
    assert cursors == [
        None,
        "after:task_001",
        "after:feat_001",
        "after:task_002",
        "after:task_001-unavailable",
        "after:task_001-again",
    ]


def test_restart_clamps_overdue_and_future_wall_schedule_to_one_interval(
    tmp_path: Path,
) -> None:
    path = audit_receipt_path(tmp_path)
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "next_scheduled_at": "2026-11-07T23:00:00+00:00",
                "next_cursor": "opaque",
            }
        ),
        encoding="utf-8",
    )
    overdue_clock = Clock(monotonic=10.0)
    overdue = _lane(tmp_path, overdue_clock, lambda *_args: AuditPassResult())
    assert overdue.deadline == 10.0

    path.write_text(
        json.dumps({"next_scheduled_at": "2099-01-01T00:00:00+00:00"}),
        encoding="utf-8",
    )
    future_clock = Clock(monotonic=20.0)
    future = _lane(tmp_path, future_clock, lambda *_args: AuditPassResult())
    assert future.deadline == 80.0


def test_failed_pass_records_retry_without_advancing_then_clears_on_success(
    tmp_path: Path,
) -> None:
    clock = Clock()
    calls = 0

    def fail(*_args) -> AuditPassResult:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("observer failed")
        return AuditPassResult(next_cursor="after-retry", counts={"observed": 1})

    lane = _lane(tmp_path, clock, fail)
    with pytest.raises(RuntimeError, match="observer failed"):
        lane.run_due_pass()
    assert read_audit_receipt(tmp_path) is None
    failure = read_audit_failure(tmp_path)
    assert failure is not None
    assert failure["code"] == "RuntimeError"
    assert failure["message"] == "observer failed"
    assert "retry without advancing" in failure["next_action"]
    assert failure["retry_seconds"] == 1.0

    clock.tick(1.0)
    assert lane.run_due_pass() is True
    assert read_audit_failure(tmp_path) is None
    assert read_audit_receipt(tmp_path)["next_cursor"] == "after-retry"


def test_bounded_pass_continues_from_opaque_cursor_without_exceeding_page_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def select(cursor, budget, **_kwargs):
        assert budget.max_items == 100
        assert 0 < budget.max_seconds <= 60
        offset = 0 if cursor is None else 100
        candidates = tuple(
            SimpleNamespace(
                work_id=f"task_{offset + index:03d}", evidence_available=True
            )
            for index in range(100)
        )
        return SimpleNamespace(
            candidates=candidates,
            next_cursor=f"opaque:{offset + 100}",
            unavailable_evidence=(),
        )

    def observe(work_id, **_kwargs):
        return SimpleNamespace(classification="healthy")

    monkeypatch.setattr(audit_lane_module, "select_audit_candidates", select)
    monkeypatch.setattr(audit_lane_module, "project_audit_observation", observe)
    cancel = threading.Event()
    first = _run_bounded_audit_pass_inline(
        tmp_path,
        None,
        cancel,
        max_items=100,
        max_seconds=60,
        monotonic=time.monotonic,
    )
    second = _run_bounded_audit_pass_inline(
        tmp_path,
        first.next_cursor,
        cancel,
        max_items=100,
        max_seconds=60,
        monotonic=time.monotonic,
    )

    assert first.counts["observed"] == second.counts["observed"] == 100
    assert first.counts["tier.task.healthy"] == 100
    assert second.counts["tier.task.healthy"] == 100
    assert first.next_cursor == "opaque:100"
    assert second.next_cursor == "opaque:200"


def test_budget_exhaustion_persists_observed_prefix_and_continues_next_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = Clock(monotonic=0.0)
    work_ids = ("task_001", "task_002", "task_003")

    def select(cursor, *_args, **_kwargs):
        offset = 0 if cursor is None else int(cursor.removeprefix("after:"))
        remaining = work_ids[offset:]
        return SimpleNamespace(
            candidates=tuple(
                SimpleNamespace(work_id=work_id, evidence_available=True)
                for work_id in remaining
            ),
            next_cursor=f"after:{len(work_ids)}",
            unavailable_evidence=(),
            continuation_cursors=tuple(
                f"after:{index}" for index in range(offset + 1, len(work_ids) + 1)
            ),
        )

    monkeypatch.setattr(audit_lane_module, "select_audit_candidates", select)

    def slow_observation(work_id, **_kwargs):
        clock.tick(0.6)
        return SimpleNamespace(classification="healthy")

    monkeypatch.setattr(
        audit_lane_module, "project_audit_observation", slow_observation
    )
    cursor = None
    results = []
    for _ in range(3):
        result = _run_bounded_audit_pass_inline(
            tmp_path,
            cursor,
            threading.Event(),
            max_items=100,
            max_seconds=0.5,
            monotonic=lambda: clock.monotonic,
        )
        results.append(result)
        cursor = result.next_cursor

    assert [result.next_cursor for result in results] == [
        "after:1",
        "after:2",
        "after:3",
    ]
    assert [result.counts["observed"] for result in results] == [1, 1, 1]


def test_unresolved_candidate_advances_without_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projected = multiprocessing.get_context("fork").Event()
    monkeypatch.setattr(
        audit_lane_module,
        "select_audit_candidates",
        lambda *_args, **_kwargs: SimpleNamespace(
            candidates=(
                SimpleNamespace(work_id="task_999", evidence_available=False),
                SimpleNamespace(work_id="task_001", evidence_available=True),
            ),
            next_cursor="after:task_001",
            unavailable_evidence=(),
            continuation_cursors=("after:task_999", "after:task_001"),
        ),
    )

    def project(work_id, **_kwargs):
        if work_id == "task_999":
            projected.set()
            raise AssertionError("missing candidate must not be projected")
        return SimpleNamespace(classification="healthy")

    monkeypatch.setattr(audit_lane_module, "project_audit_observation", project)
    result = _run_bounded_audit_pass_inline(
        tmp_path,
        None,
        threading.Event(),
        max_items=100,
        max_seconds=60,
        monotonic=time.monotonic,
    )

    assert not projected.is_set()
    assert result.next_cursor == "after:task_001"
    assert result.counts["observed"] == 2
    assert result.counts["healthy"] == 1
    assert result.counts["unavailable_evidence"] == 1
    assert result.reassessed_candidates == ("task_001",)


def test_candidate_timeout_advances_unavailable_candidate_without_stalling_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work_ids = ("task_001", "task_002", "feat_001")

    def select(cursor, *_args, **_kwargs):
        offset = 0 if cursor is None else int(cursor.removeprefix("after:"))
        return SimpleNamespace(
            candidates=tuple(
                SimpleNamespace(work_id=value, evidence_available=True)
                for value in work_ids[offset:]
            ),
            next_cursor=f"after:{len(work_ids)}",
            unavailable_evidence=(),
            continuation_cursors=tuple(
                f"after:{index}" for index in range(offset + 1, len(work_ids) + 1)
            ),
        )

    attempts: list[str] = []

    def observe(work_id, **_kwargs):
        attempts.append(work_id)
        if work_id == "task_002" and attempts.count(work_id) == 1:
            raise subprocess.TimeoutExpired(["git", "log"], 0.1)
        return SimpleNamespace(classification="healthy")

    monkeypatch.setattr(audit_lane_module, "select_audit_candidates", select)
    monkeypatch.setattr(audit_lane_module, "project_audit_observation", observe)
    first = _run_bounded_audit_pass_inline(
        tmp_path,
        None,
        threading.Event(),
        max_items=100,
        max_seconds=60,
        monotonic=time.monotonic,
    )
    second = _run_bounded_audit_pass_inline(
        tmp_path,
        first.next_cursor,
        threading.Event(),
        max_items=100,
        max_seconds=60,
        monotonic=time.monotonic,
    )

    assert first.next_cursor == "after:3"
    assert first.counts["observed"] == 2
    assert first.counts["unavailable_evidence"] == 1
    assert first.reassessed_candidates == ("task_001", "feat_001")
    assert second.next_cursor == "after:3"
    assert attempts == ["task_001", "task_002", "feat_001"]


def test_repeated_first_candidate_timeout_still_reaches_later_tiers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    work_ids = ("task_001", "feat_001", "epic_001")

    def select(cursor, *_args, **_kwargs):
        offset = 0 if cursor is None else int(cursor.removeprefix("after:"))
        return SimpleNamespace(
            candidates=(
                SimpleNamespace(work_id=work_ids[offset], evidence_available=True),
            ),
            next_cursor=f"after:{(offset + 1) % len(work_ids)}",
            unavailable_evidence=(),
            continuation_cursors=(f"after:{(offset + 1) % len(work_ids)}",),
        )

    attempted: list[str] = []

    def observe(work_id, **_kwargs):
        attempted.append(work_id)
        if work_id == "task_001":
            raise subprocess.TimeoutExpired(["git", "log"], 0.1)
        return SimpleNamespace(classification="healthy")

    monkeypatch.setattr(audit_lane_module, "select_audit_candidates", select)
    monkeypatch.setattr(audit_lane_module, "project_audit_observation", observe)
    first = _run_bounded_audit_pass_inline(
        tmp_path,
        None,
        threading.Event(),
        max_items=1,
        max_seconds=60,
        monotonic=time.monotonic,
    )
    second = _run_bounded_audit_pass_inline(
        tmp_path,
        first.next_cursor,
        threading.Event(),
        max_items=1,
        max_seconds=60,
        monotonic=time.monotonic,
    )
    third = _run_bounded_audit_pass_inline(
        tmp_path,
        second.next_cursor,
        threading.Event(),
        max_items=1,
        max_seconds=60,
        monotonic=time.monotonic,
    )
    fourth = _run_bounded_audit_pass_inline(
        tmp_path,
        third.next_cursor,
        threading.Event(),
        max_items=1,
        max_seconds=60,
        monotonic=time.monotonic,
    )

    assert [
        first.next_cursor,
        second.next_cursor,
        third.next_cursor,
        fourth.next_cursor,
    ] == [
        "after:1",
        "after:2",
        "after:0",
        "after:1",
    ]
    assert first.counts["unavailable_evidence"] == 1
    assert first.counts["observed"] == 0
    assert second.counts["healthy"] == third.counts["healthy"] == 1
    assert fourth.counts["unavailable_evidence"] == 1
    assert attempted == [*work_ids, "task_001"]


def test_fifo_timeout_reaps_observer_before_workspace_claim_is_released(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    sidecars = root / ".cascade"
    sidecars.mkdir(exist_ok=True)
    fifo = sidecars / "executions.json"
    os.mkfifo(fifo)

    def bounded(cursor, cancel):
        return run_bounded_audit_pass(root, cursor, cancel, max_seconds=0.05)

    first = HealthAuditLane(
        root=root,
        config=HealthAuditConfig(enabled=True, interval_seconds=60),
        run_pass=bounded,
        jitter=lambda *_args: 0.0,
    )
    finished = threading.Event()
    errors: list[BaseException] = []

    def run_first() -> None:
        try:
            first.run_due_pass()
        except BaseException as exc:
            errors.append(exc)
        finally:
            finished.set()

    thread = threading.Thread(target=run_first)
    thread.start()
    competing_claim = _WorkspaceClaim(root)
    deadline = time.monotonic() + 1.0
    while competing_claim.acquire():
        competing_claim.release()
        if time.monotonic() >= deadline:
            raise AssertionError("audit pass did not acquire the workspace claim")
        time.sleep(0.005)
    assert finished.wait(2)
    thread.join(1)
    assert not thread.is_alive()
    assert len(errors) == 1
    assert isinstance(errors[0], AuditPassTimedOut)

    # A blocked FIFO reader would make this nonblocking writer open succeed.
    with pytest.raises(OSError) as exc_info:
        os.open(fifo, os.O_WRONLY | os.O_NONBLOCK)
    assert exc_info.value.errno == errno.ENXIO
    assert competing_claim.acquire()
    competing_claim.release()


def test_timeout_kills_term_ignoring_git_descendant_before_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Audit Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Audit Feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Blocked Git",
        tier="task",
        status="active",
        parent="feat_001",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    pid_file = tmp_path / "git-helper.pid"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env python3\n"
        "import os, signal, time\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    with open(os.environ['AUDIT_HELPER_PID'], 'w') as handle:\n"
        "        handle.write(str(os.getpid()))\n"
        "    while True: time.sleep(1)\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "while True: time.sleep(1)\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    monkeypatch.setenv("AUDIT_HELPER_PID", str(pid_file))
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ['PATH']}")

    started = time.monotonic()
    result = run_bounded_audit_pass(root, None, threading.Event(), max_seconds=8.0)
    assert time.monotonic() - started < 9.0
    assert result.counts["unavailable_evidence"] >= 1
    assert result.counts["healthy"] == 0
    helper_pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 1.0
    while not _process_gone_or_zombie(helper_pid) and time.monotonic() < deadline:
        time.sleep(0.01)
    assert _process_gone_or_zombie(helper_pid)


def _exit_observer_with_helper(sender, helper_file: Path) -> None:
    os.setsid()
    pid = os.fork()
    if pid == 0:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        helper_file.write_text(str(os.getpid()), encoding="utf-8")
        while True:
            time.sleep(1)
    while not helper_file.exists():
        time.sleep(0.01)
    os._exit(1)


def test_process_startup_counts_against_pass_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    context = multiprocessing.get_context("spawn")

    class SlowStartProcess:
        pid = None

        def start(self) -> None:
            time.sleep(0.06)

        def is_alive(self) -> bool:
            return False

        def join(self, timeout=None) -> None:
            pass

    class SlowStartContext:
        Event = context.Event
        Pipe = context.Pipe

        def Process(self, **_kwargs):
            return SlowStartProcess()

    monkeypatch.setattr(
        audit_lane_module.multiprocessing,
        "get_context",
        lambda *_: SlowStartContext(),
    )
    with pytest.raises(AuditPassTimedOut):
        run_bounded_audit_pass(tmp_path, None, threading.Event(), max_seconds=0.05)


def test_exited_observer_reaps_surviving_helper_before_return(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    helper_file = tmp_path / "helper.pid"
    context = multiprocessing.get_context("spawn")

    class ExitContext:
        Event = context.Event
        Pipe = context.Pipe

        def Process(self, *, args, **kwargs):
            return context.Process(
                target=_exit_observer_with_helper,
                args=(args[0], helper_file),
                name=kwargs["name"],
                daemon=kwargs["daemon"],
            )

    monkeypatch.setattr(
        audit_lane_module.multiprocessing, "get_context", lambda *_: ExitContext()
    )

    try:
        with pytest.raises(RuntimeError, match="observer exited without a result"):
            run_bounded_audit_pass(root, None, threading.Event(), max_seconds=10.0)
        helper_pid = int(helper_file.read_text(encoding="utf-8"))
        deadline = time.monotonic() + 1.0
        while not _process_gone_or_zombie(helper_pid):
            if time.monotonic() >= deadline:
                raise AssertionError("observer helper survived claim release")
            time.sleep(0.01)
    finally:
        if helper_file.exists():
            try:
                os.kill(int(helper_file.read_text(encoding="utf-8")), 9)
            except ProcessLookupError:
                pass


def test_spawned_observer_does_not_inherit_parent_board_scan_lock(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Independent Audit",
        tier="epic",
        status="active",
    )
    entered = threading.Event()
    release = threading.Event()

    def hold_parent_lock() -> None:
        with board_store._scan_meta_cache_lock:
            entered.set()
            assert release.wait(15)

    holder = threading.Thread(target=hold_parent_lock)
    holder.start()
    assert entered.wait(2)
    try:
        result = run_bounded_audit_pass(root, None, threading.Event(), max_seconds=10.0)
        assert result.counts["observed"] == 1
    finally:
        release.set()
        holder.join(2)
    assert not holder.is_alive()


def test_workspace_claim_allows_only_one_concurrent_pass(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()

    def blocking(*_args) -> AuditPassResult:
        entered.set()
        assert release.wait(2)
        return AuditPassResult(counts={"passes": 1})

    first = HealthAuditLane(
        root=tmp_path,
        config=HealthAuditConfig(enabled=True, interval_seconds=60),
        run_pass=blocking,
        jitter=lambda *_args: 0.0,
    )
    second_calls = 0

    def second_pass(*_args) -> AuditPassResult:
        nonlocal second_calls
        second_calls += 1
        return AuditPassResult()

    second = HealthAuditLane(
        root=tmp_path,
        config=HealthAuditConfig(enabled=True, interval_seconds=60),
        run_pass=second_pass,
    )
    thread = threading.Thread(target=first.run_due_pass)
    thread.start()
    assert entered.wait(2)
    assert second.run_due_pass() is False
    assert second_calls == 0
    release.set()
    thread.join(2)
    assert not thread.is_alive()


def test_trunk_and_owned_worktree_share_cross_process_claim(tmp_path: Path) -> None:
    trunk = tmp_path / "product"
    trunk.mkdir()
    subprocess.run(["git", "init", "-q", str(trunk)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(trunk),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-q",
            "--allow-empty",
            "-m",
            "init",
        ],
        check=True,
    )
    child = trunk / ".cascade" / "worktrees" / "feat_feat_test"
    child.parent.mkdir(parents=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(trunk),
            "worktree",
            "add",
            "-q",
            "-b",
            "feat/test",
            str(child),
        ],
        check=True,
    )
    assert canonical_audit_root(child) == trunk
    assert audit_receipt_path(child) == audit_receipt_path(trunk)

    probe = (
        "import sys; from pathlib import Path; "
        "from cascade.watchdog.audit_lane import _WorkspaceClaim; "
        "claim = _WorkspaceClaim(Path(sys.argv[1])); "
        "acquired = claim.acquire(); print(int(acquired)); claim.release()"
    )

    def probe_child() -> str:
        return subprocess.run(
            [sys.executable, "-c", probe, str(child)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    claim = _WorkspaceClaim(trunk)
    assert claim.acquire()
    try:
        assert probe_child() == "0"
    finally:
        claim.release()
    assert probe_child() == "1"


def test_tracking_owned_worktree_maps_to_product_claim(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    product = tmp_path / "product"
    tracking = tmp_path / "tracking"
    child = tracking / ".cascade" / "worktrees" / "task_task_test"
    child.mkdir(parents=True)
    monkeypatch.setattr(
        "cascade.watchdog.audit_lane.get_project_context",
        lambda: ProjectContext.split(product, tracking),
    )
    assert canonical_audit_root(child) == product
    assert audit_receipt_path(child) == audit_receipt_path(product)


def test_lane_adopts_receipt_completed_by_another_process(tmp_path: Path) -> None:
    clock = Clock()
    calls = 0

    def count(*_args) -> AuditPassResult:
        nonlocal calls
        calls += 1
        return AuditPassResult(counts={"passes": 1})

    first = _lane(tmp_path, clock, count, jitter=lambda *_args: 0.0)
    second = _lane(tmp_path, clock, count, jitter=lambda *_args: 0.0)
    assert first.run_due_pass() is True
    assert second.run_due_pass() is False
    assert calls == 1
    assert second.deadline == 160.0


def test_disabled_lane_creates_no_thread_or_runtime_files(tmp_path: Path) -> None:
    lane = HealthAuditLane(
        root=tmp_path,
        config=HealthAuditConfig(enabled=False, interval_seconds=60),
        run_pass=lambda *_args: AuditPassResult(),
    ).start()
    lane.stop()
    assert not (tmp_path / ".cascade").exists()


def test_disabled_lane_accepts_manual_pass_without_moving_periodic_deadline(
    tmp_path: Path,
) -> None:
    clock = Clock(monotonic=20.0)
    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()

    def run(*_args) -> AuditPassResult:
        entered.set()
        assert release.wait(2)
        return AuditPassResult(counts={"manual": 1})

    lane = HealthAuditLane(
        root=tmp_path,
        config=HealthAuditConfig(enabled=False, interval_seconds=60),
        run_pass=run,
        monotonic=lambda: clock.monotonic,
        utc_now=lambda: clock.utc,
        handoff=lambda _ids: completed.set(),
    ).start()
    deadline = lane.deadline
    try:
        assert lane.request_manual_pass() is True
        assert entered.wait(2)
        assert lane.request_manual_pass() is False
        release.set()
        assert completed.wait(2)
        assert lane.deadline == deadline
        assert read_audit_receipt(tmp_path)["counts"] == {"manual": 1}
    finally:
        release.set()
        lane.stop(timeout=2)


def test_manual_request_coalesces_with_running_periodic_pass(tmp_path: Path) -> None:
    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()
    calls = 0

    def run(*_args) -> AuditPassResult:
        nonlocal calls
        calls += 1
        entered.set()
        assert release.wait(2)
        return AuditPassResult(counts={"periodic": 1})

    lane = HealthAuditLane(
        root=tmp_path,
        config=HealthAuditConfig(enabled=True, interval_seconds=60),
        run_pass=run,
        handoff=lambda _ids: completed.set(),
        jitter=lambda *_args: 0.0,
    ).start()
    try:
        assert entered.wait(2)
        assert lane.request_manual_pass() is False
        release.set()
        assert completed.wait(2)
        assert calls == 1
    finally:
        release.set()
        lane.stop(timeout=2)


def test_disabled_manual_failure_retries_after_bounded_cooldown(
    tmp_path: Path,
) -> None:
    attempts = 0
    retried = threading.Event()

    def run(*_args) -> AuditPassResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary observer failure")
        retried.set()
        return AuditPassResult(counts={"manual": 1})

    lane = HealthAuditLane(
        root=tmp_path,
        config=HealthAuditConfig(enabled=False, interval_seconds=60),
        run_pass=run,
    ).start()
    deadline = lane.deadline
    try:
        assert lane.request_manual_pass() is True
        assert retried.wait(2.5)
        assert attempts == 2
        assert lane.deadline == deadline
        limit = time.monotonic() + 1
        receipt = read_audit_receipt(tmp_path)
        while receipt is None and time.monotonic() < limit:
            time.sleep(0.01)
            receipt = read_audit_receipt(tmp_path)
        assert receipt is not None
        assert receipt["counts"] == {"manual": 1}
    finally:
        lane.stop(timeout=2)


def test_recovery_handoff_runs_after_workspace_claim_is_released(
    tmp_path: Path,
) -> None:
    acquired = []

    def handoff(_ids: tuple[str, ...]) -> None:
        claim = _WorkspaceClaim(tmp_path)
        acquired.append(claim.acquire())
        claim.release()

    lane = HealthAuditLane(
        root=tmp_path,
        config=HealthAuditConfig(enabled=True, interval_seconds=60),
        run_pass=lambda *_args: AuditPassResult(
            counts={"proven_incident": 1}, incident_work_ids=("task_001",)
        ),
        handoff=handoff,
        jitter=lambda *_args: 0.0,
    )
    assert lane.run_due_pass() is True
    assert acquired == [True]


def test_lane_cleanup_does_not_set_caller_stop_but_observes_it(
    tmp_path: Path,
) -> None:
    operator_stop = threading.Event()
    observed = threading.Event()
    cancelled = threading.Event()

    def run(_cursor: str | None, cancel: threading.Event) -> AuditPassResult:
        observed.set()
        assert cancel.wait(2)
        cancelled.set()
        return AuditPassResult()

    lane = HealthAuditLane(
        root=tmp_path,
        config=HealthAuditConfig(enabled=True, interval_seconds=60),
        run_pass=run,
        stop_event=operator_stop,
    ).start()
    try:
        assert observed.wait(2)
        operator_stop.set()
        assert cancelled.wait(1)
    finally:
        lane.stop(timeout=2)
    assert not (lane._thread and lane._thread.is_alive())

    fresh_stop = threading.Event()
    idle_lane = HealthAuditLane(
        root=tmp_path,
        config=HealthAuditConfig(enabled=False, interval_seconds=60),
        run_pass=run,
        stop_event=fresh_stop,
    )
    idle_lane.stop()
    assert not fresh_stop.is_set()


def test_omitted_health_audit_table_keeps_default_on_configuration(tmp_path: Path) -> None:
    (tmp_path / "cascade.toml").write_text(
        "[automation]\nenabled = true\n", encoding="utf-8"
    )
    config = read_health_audit_config(tmp_path)
    assert config.enabled is True
    assert config.interval_seconds == 1800
