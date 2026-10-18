"""Read/write amendment sidecars at docs/epics/2_active/_amendments/."""

from __future__ import annotations

import json
import re
from pathlib import Path

from cascade.amendments.diff import unified_section_diff
from cascade.amendments.types import Amendment
from cascade.board.context import resolve_root
from cascade.board.paths import slugify

_AMD_ID_RE = re.compile(r"^amd_(\d+)$")
_AMENDMENTS_DIR = Path("docs") / "epics" / "2_active" / "_amendments"
_OPEN_STATES = frozenset({"pending", "revise_pending"})


class AmendmentStoreError(Exception):
    """Invalid amendment operation."""


class AmendmentNotFound(AmendmentStoreError):
    """No amendment with this id or path."""


def section_slug(section: str) -> str:
    """Stable filename slug for a section title (feat_006 basename segment)."""

    return slugify(section)


def amendments_dir(*, root: Path) -> Path:
    repo = resolve_root(root)
    return repo / _AMENDMENTS_DIR


def sidecar_basename(feature_id: str, section: str) -> str:
    return f"{feature_id}_{section_slug(section)}"


def sidecar_paths(feature_id: str, section: str, *, root: Path) -> tuple[Path, Path]:
    repo = resolve_root(root)
    base = sidecar_basename(feature_id, section)
    folder = amendments_dir(root=repo)
    return folder / f"{base}.diff.md", folder / f"{base}.meta.json"


def allocate_amd_id(*, root: Path) -> str:
    """Next monotonic ``amd_NNN`` by scanning existing ``.meta.json`` files."""

    repo = resolve_root(root)
    highest = 0
    directory = amendments_dir(root=repo)
    if directory.is_dir():
        for path in sorted(directory.glob("*.meta.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            if not isinstance(raw, dict):
                continue
            amd_id = raw.get("id")
            if not isinstance(amd_id, str):
                continue
            match = _AMD_ID_RE.match(amd_id)
            if match:
                highest = max(highest, int(match.group(1)))
    return f"amd_{highest + 1:03d}"


def write_sidecar(
    amendment: Amendment,
    epic_body_at_rev: str,
    *,
    root: Path,
) -> Amendment:
    """Write ``.diff.md`` and sibling ``.meta.json``; return record with paths set."""

    repo = resolve_root(root)
    amd_id = amendment.id.strip() if amendment.id else ""
    if not amd_id:
        amd_id = allocate_amd_id(root=repo)

    diff_path, meta_path = sidecar_paths(
        amendment.feature_id,
        amendment.section,
        root=repo,
    )
    diff_text = unified_section_diff(
        epic_body_at_rev,
        amendment.section,
        amendment.proposed_text,
        epic_label=amendment.epic_id,
    )
    record = Amendment(
        id=amd_id,
        feature_id=amendment.feature_id,
        epic_id=amendment.epic_id,
        section=amendment.section,
        diff_path=diff_path.relative_to(repo),
        proposed_text=amendment.proposed_text,
        rationale=amendment.rationale,
        state=amendment.state,
        created=amendment.created,
        revised_text=amendment.revised_text,
        reject_reason=amendment.reject_reason,
    )

    diff_path.parent.mkdir(parents=True, exist_ok=True)
    diff_path.write_text(diff_text, encoding="utf-8")
    meta_path.write_text(
        json.dumps(record.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return record


def read_amendment(amd_id: str, *, root: Path) -> Amendment:
    if not _AMD_ID_RE.match(amd_id):
        raise AmendmentNotFound(amd_id)
    repo = resolve_root(root)
    directory = amendments_dir(root=repo)
    if not directory.is_dir():
        raise AmendmentNotFound(amd_id)
    for path in directory.glob("*.meta.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(raw, dict) and raw.get("id") == amd_id:
            record = Amendment.from_dict(raw)
            return _resolve_paths(record, repo)
    raise AmendmentNotFound(amd_id)


def load_by_path(diff_path: Path | str, *, root: Path) -> Amendment:
    repo = resolve_root(root)
    path = Path(diff_path)
    if not path.is_absolute():
        path = (repo / path).resolve()
    else:
        path = path.resolve()
    if not path.name.endswith(".diff.md"):
        raise AmendmentNotFound(str(diff_path))
    meta_path = path.with_name(path.name.replace(".diff.md", ".meta.json"))
    if not meta_path.is_file():
        raise AmendmentNotFound(str(diff_path))
    raw = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise AmendmentNotFound(str(diff_path))
    record = Amendment.from_dict(raw)
    return _resolve_paths(record, repo)


def update_amendment(record: Amendment, *, root: Path) -> Amendment:
    """Persist state transitions and optional revise/reject fields."""

    repo = resolve_root(root)
    _, meta_path = sidecar_paths(record.feature_id, record.section, root=repo)
    if not meta_path.is_file():
        raise AmendmentNotFound(record.id)
    stored = Amendment.from_dict(json.loads(meta_path.read_text(encoding="utf-8")))
    if stored.id != record.id:
        raise AmendmentStoreError("record id does not match sidecar basename owner")

    resolved = _resolve_paths(record, repo)
    meta_path.write_text(
        json.dumps(resolved.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return resolved


def list_pending_for_epic(epic_id: str, *, root: Path) -> list[Amendment]:
    return [
        row
        for row in _load_all(root=root)
        if row.epic_id == epic_id and row.state in _OPEN_STATES
    ]


def find_open_for_section(epic_id: str, section: str, *, root: Path) -> Amendment | None:
    for row in list_pending_for_epic(epic_id, root=root):
        if row.section == section:
            return row
    return None


def _load_all(*, root: Path) -> list[Amendment]:
    repo = resolve_root(root)
    directory = amendments_dir(root=repo)
    if not directory.is_dir():
        return []
    rows: list[Amendment] = []
    for path in sorted(directory.glob("*.meta.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                rows.append(_resolve_paths(Amendment.from_dict(raw), repo))
        except (OSError, json.JSONDecodeError, ValueError, TypeError):
            continue
    return rows


def _resolve_paths(record: Amendment, repo: Path) -> Amendment:
    diff = record.diff_path
    if not diff.is_absolute():
        diff = repo / diff
    rel = diff.relative_to(repo)
    return Amendment(
        id=record.id,
        feature_id=record.feature_id,
        epic_id=record.epic_id,
        section=record.section,
        diff_path=rel,
        proposed_text=record.proposed_text,
        rationale=record.rationale,
        state=record.state,
        created=record.created,
        revised_text=record.revised_text,
        reject_reason=record.reject_reason,
    )

