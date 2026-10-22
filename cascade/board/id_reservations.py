"""In-process work id reservations shared by legacy and hierarchical allocators."""

from __future__ import annotations

from contextvars import ContextVar

from cascade.board.types import WorkId

_reserved_ids: ContextVar[frozenset[str]] = ContextVar(
    "cascade_reserved_ids",
    default=frozenset(),
)


def reset_id_reservations() -> None:
    """Drop in-memory ids reserved by allocate_id. Tests isolate calls with this."""

    _reserved_ids.set(frozenset())


def reserve_work_id(work_id: WorkId) -> None:
    """Remember ``work_id`` so a subsequent allocation cannot reuse it in-process."""

    reserved = set(_reserved_ids.get())
    reserved.add(work_id)
    _reserved_ids.set(frozenset(reserved))


def release_work_id(work_id: WorkId) -> None:
    """Drop an in-process reservation after a failed persist attempt."""

    reserved = set(_reserved_ids.get())
    reserved.discard(work_id)
    _reserved_ids.set(frozenset(reserved))


def reserved_work_ids() -> frozenset[str]:
    """In-process ids already handed out by an allocator."""

    return _reserved_ids.get()
