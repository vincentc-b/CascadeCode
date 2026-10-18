"""Amendment sidecar persistence (feat_006 task_026)."""

from cascade.amendments.diff import extract_section_body, unified_section_diff
from cascade.amendments.store import (
    AmendmentNotFound,
    AmendmentStoreError,
    allocate_amd_id,
    amendments_dir,
    find_open_for_section,
    list_pending_for_epic,
    load_by_path,
    read_amendment,
    section_slug,
    sidecar_basename,
    sidecar_paths,
    update_amendment,
    write_sidecar,
)
from cascade.amendments.types import Amendment, AmendmentState

__all__ = [
    "Amendment",
    "AmendmentNotFound",
    "AmendmentState",
    "AmendmentStoreError",
    "allocate_amd_id",
    "amendments_dir",
    "extract_section_body",
    "find_open_for_section",
    "list_pending_for_epic",
    "load_by_path",
    "read_amendment",
    "section_slug",
    "sidecar_basename",
    "sidecar_paths",
    "unified_section_diff",
    "update_amendment",
    "write_sidecar",
]
