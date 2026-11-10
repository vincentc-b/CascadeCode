"""Durable agent investigations independent of finite deterministic audit probes."""
from __future__ import annotations

import fcntl
import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cascade.watchdog.audit_lane import (
    _read_runtime_json, _write_json_atomically, canonical_audit_root,
)

_log = logging.getLogger(__name__)


def _home(root: Path) -> Path:
    return canonical_audit_root(root) / '.cascade' / 'health_audit'


def enqueue_investigations(root: Path, requests: tuple[dict, ...]) -> None:
    """Persist before the scanner advances its receipt; delivery is replayable."""
    if not requests:
        return
    for request in requests:
        payload = {'requests': [request]}
        path = _home(root) / 'agent_outbox' / f'{time.time_ns()}-{uuid.uuid4().hex}.json'
        _write_json_atomically(path, payload)


def _read(path: Path) -> dict:
    raw = _read_runtime_json(path)
    return json.loads(raw) if raw is not None else {}


def investigation_schedule(root: Path) -> dict:
    return {**_read(_home(root) / 'agent_schedule.json'),
            'last_error': _read(_home(root) / 'agent_error.json') or None,
            'admission': {k: v for k, v in _read(_home(root) / 'agent_activity.json').items()
                          if k not in {'first_seen', 'owners', 'targets'}}}


def request_agent_review(root: Path) -> None:
    _write_json_atomically(_home(root) / 'agent_review_requested.json', {'requested_at': time.time()})


_MIN_ACTIVE_AGE_SECONDS = 20 * 60


def _agent_admission(root: Path, now: float) -> dict:
    """Use observed active tenure, never the date a backlog brief was created.

    Persist first-seen times across restarts. Remove retired items so a later
    observed reactivation receives a fresh grace period. Missing evidence never
    permits paid work. No model or provider calls are made here.
    """
    from cascade.board.context import resolve_tracking_root
    from cascade.workspace.integration_worktree import merged_board_readonly

    board = merged_board_readonly(resolve_tracking_root(root))
    live = {m.id: m for m in board.by_id.values()
            if m.tier in {'epic', 'feature', 'task'} and m.status in {'active', 'blocked'}}
    path = _home(root) / 'agent_activity.json'
    previous = _read(path).get('first_seen', {})
    first_seen = {}
    for work_id in live:
        stamp = previous.get(work_id, now)
        if not isinstance(stamp, (int, float)) or not 0 <= stamp <= now:
            stamp = now
        first_seen[work_id] = stamp
    oldest = min(first_seen.values(), default=now)
    ready = bool(live) and now - oldest >= _MIN_ACTIVE_AGE_SECONDS
    owners = [m.id for m in live.values() if m.tier in {'epic', 'feature'}]
    targets = [m.id for m in board.by_id.values()
               if m.id in owners or m.parent in owners]
    result = {'first_seen': first_seen, 'live_items': len(live),
              'owners': owners, 'targets': targets, 'ready': ready,
              'oldest_age_seconds': now - oldest if live else None,
              'minimum_age_seconds': _MIN_ACTIVE_AGE_SECONDS,
              'reason': 'eligible' if ready else ('no_live_work' if not live else 'grace_period'),
              'checked_at': now}
    _write_json_atomically(path, result)
    return result


class AuditInvestigationWorker:
    """Queue real owner-agent turns without holding audit or lifecycle locks.

    Periodic reviews deliberately do not require a known incident class. Their
    short candidate scan is independent of historical audit/probe timeouts.
    """
    def __init__(self, root: Path, *, interval_seconds: int = 1800, enabled: bool = True):
        self.root = Path(root).resolve()
        self.interval_seconds = interval_seconds
        self.enabled = enabled
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, name='health-audit-investigations', daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self, timeout: float | None = None) -> None:
        self._stop.set()
        self._thread.join(timeout)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self.run_once()
            except Exception as exc:
                # Preserve the outbox; operators see delivery failure without
                # model/provider output or arbitrary exception payloads.
                _log.warning('agent audit delivery failed (%s)', type(exc).__name__)
                _write_json_atomically(_home(self.root) / 'agent_error.json', {
                    'at': time.time(), 'error': type(exc).__name__,
                    'next_action': 'Investigation delivery will retry; inspect the audit agent outbox.',
                })
            self._stop.wait(5)

    def run_once(self, *, now: float | None = None) -> None:
        from cascade.watchdog.audit_investigation import request_investigation, replay_pending_investigations, read_investigation_cases

        now = time.time() if now is None else now
        home = _home(self.root)
        home.mkdir(parents=True, exist_ok=True)
        with (home / 'agent.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            manual_path = home / 'agent_review_requested.json'
            manual = manual_path.exists()
            schedule = investigation_schedule(self.root)
            pending_cases = read_investigation_cases(root=self.root, limit=1000)
            queued = any(c['status'] == 'queued' for c in pending_cases)
            outbox = any((home / 'agent_outbox').glob('*.json'))
            due = self.enabled and float(schedule.get('next_due', 0)) <= now
            # Observe activity once per minute even while idle, but do not
            # rebuild the board every five seconds just to check an empty queue.
            last_check = schedule.get('admission', {}).get('checked_at', 0)
            if not manual and now - last_check < 60:
                if not schedule.get('admission', {}).get('ready') or not (queued or outbox or due):
                    return
            admission = _agent_admission(self.root, now)
            if not admission['live_items'] or (not manual and not admission['ready']):
                _write_json_atomically(home / 'agent_schedule.json', {
                    **{k: v for k, v in schedule.items() if k not in {'admission', 'last_error'}},
                    'next_due': now + 60, 'scheduled': 0,
                })
                if not admission['live_items']:
                    manual_path.unlink(missing_ok=True)
                return
            errors = []
            if self.enabled or manual:
                try:
                    self._schedule_owner_reviews(now, force=manual)
                    if not investigation_schedule(self.root).get('cursor'):
                        manual_path.unlink(missing_ok=True)
                except Exception as exc:
                    errors.append({'work_id': 'periodic_review', 'error': type(exc).__name__})
            try:
                replay_pending_investigations(root=self.root, limit=12,
                    eligible_owner_ids=set(admission['owners']))
            except Exception as exc:
                errors.append({'work_id': 'pending_delivery', 'error': type(exc).__name__})
            # Bound each drain; unfinished envelopes remain durable. Replaying
            # an already-delivered prefix is safe through case deduplication.
            remaining = 12
            for path in sorted((home / 'agent_outbox').glob('*.json')):
                try:
                    requests = _read(path).get('requests', [])
                except Exception as exc:
                    errors.append({'work_id': path.stem, 'error': type(exc).__name__})
                    continue
                pending = []
                for request in requests:
                    if request['work_id'] not in admission['targets']:
                        continue  # Retired/unstaffed history is not an agent dispatch target.
                    if not remaining or self._stop.is_set() or request.get('retry_after', 0) > now:
                        pending.append(request)
                        if request.get('delivery_error'):
                            errors.append({'work_id': request['work_id'], 'error': request['delivery_error']})
                        continue
                    remaining -= 1
                    try:
                        request_investigation(
                            root=self.root, work_id=request['work_id'], reason=request['reason'],
                            evidence=request.get('evidence', {}),
                            cooldown_seconds=self.interval_seconds, now=datetime.fromtimestamp(now, timezone.utc),
                        )
                    except Exception as exc:
                        request = {**request, 'delivery_error': type(exc).__name__, 'retry_after': now + 60}
                        pending.append(request)
                        errors.append({'work_id': request['work_id'], 'error': type(exc).__name__})
                if pending:
                    _write_json_atomically(path, {'requests': pending})
                else:
                    path.unlink(missing_ok=True)
                if not remaining or self._stop.is_set():
                    break
            if errors:
                _write_json_atomically(home / 'agent_error.json', {'at': now, 'delivery_failures': errors[:20]})
            else:
                (home / 'agent_error.json').unlink(missing_ok=True)

    def _schedule_owner_reviews(self, now: float, *, force: bool = False) -> None:
        from cascade.board.context import resolve_tracking_root
        from cascade.workspace.integration_worktree import merged_board_readonly

        schedule = investigation_schedule(self.root)
        if not force and float(schedule.get('next_due', 0)) > now:
            return
        board = merged_board_readonly(resolve_tracking_root(self.root))
        owners = sorted((m for m in board.by_id.values()
                         if m.tier in {'feature', 'epic'} and m.status in {'active', 'blocked'}),
                        key=lambda m: m.id)
        cursor = str(schedule.get('cursor') or '')
        pending = [m for m in owners if m.id > cursor]
        page = pending[:16]
        requests = tuple({
            'work_id': m.id, 'reason': 'periodic_agent_review',
            'evidence': {
                'status': m.status,
                'child_statuses': {c: board.by_id[c].status if c in board.by_id else 'missing'
                                   for c in m.children[:20]},
                'monitoring_blockers': [
                    {'child_id': b.child_id, 'reason': b.reason, 'incident_id': b.incident_id}
                    for b in m.monitoring_blockers[:10]],
            },
        } for m in page)
        # Reassess reports at the review cadence, never on every five-second tick.
        # Refresh canonical state; previous reports travel with the case prompt.
        if not cursor:
            from cascade.watchdog.audit_investigation import read_investigation_cases
            followups = []
            for case in read_investigation_cases(root=self.root, limit=1000):
                work = board.by_id.get(case['work_id'])
                if (case['status'] == 'reassess' and case['reason'] != 'periodic_agent_review'
                        and work is not None and work.status not in {'completed', 'cancelled'}
                        and datetime.fromisoformat(case['next_reassessment_at']).timestamp() <= now):
                    evidence = {k: v for k, v in case['evidence'].items() if k != 'canonical'}
                    evidence['status'] = work.status
                    followups.append({'work_id': work.id, 'reason': case['reason'], 'evidence': evidence})
            requests += tuple(followups)
        enqueue_investigations(self.root, requests)
        more = len(pending) > len(page)
        _write_json_atomically(_home(self.root) / 'agent_schedule.json', {
            'last_scheduled_at': now, 'next_due': now if more else now + self.interval_seconds,
            'cursor': page[-1].id if more else '', 'active_owners': len(owners),
            'scheduled': len(page), 'interval_seconds': self.interval_seconds,
        })
