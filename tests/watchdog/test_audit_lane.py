from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cascade.watchdog.audit_lane import (
    AuditPassResult,
    HealthAuditLane,
    audit_receipt_path,
    read_audit_receipt,
)
from cascade.watchdog.config import HealthAuditConfig, health_audit_periodic_opted_in


class Clock:
    def __init__(
        self, *, monotonic: float = 100.0, utc: datetime | None = None
    ) -> None:
        self.monotonic = monotonic
        self.utc = utc or datetime(2026, 11, 8, tzinfo=timezone.utc)

    def tick(self, seconds: float) -> None:
        self.monotonic += seconds
        self.utc += timedelta(seconds=seconds)


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


def test_failed_pass_does_not_advance_or_create_receipt(tmp_path: Path) -> None:
    clock = Clock()

    def fail(*_args) -> AuditPassResult:
        raise RuntimeError("observer failed")

    lane = _lane(tmp_path, clock, fail)
    with pytest.raises(RuntimeError, match="observer failed"):
        lane.run_due_pass()
    assert read_audit_receipt(tmp_path) is None


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


def test_periodic_startup_requires_explicit_health_audit_table(tmp_path: Path) -> None:
    (tmp_path / "cascade.toml").write_text(
        "[automation]\nenabled = true\n", encoding="utf-8"
    )
    assert health_audit_periodic_opted_in(tmp_path) is False
    (tmp_path / "cascade.toml").write_text(
        "[automation.health_audit]\nenabled = true\n", encoding="utf-8"
    )
    assert health_audit_periodic_opted_in(tmp_path) is True
