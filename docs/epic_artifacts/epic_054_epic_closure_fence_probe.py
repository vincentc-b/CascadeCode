"""Read pinned source and probe its closure writer without touching a registry.

This is function-boundary evidence, not a full lifecycle concurrency test.
Run from the repository root with the declared Python interpreter.
"""
from __future__ import annotations

import ast
import dataclasses
import hashlib
import json
from pathlib import Path
import subprocess
import typing
from urllib.parse import urlsplit

REVISION = "514c54477b00f42a28a914a4d2ea2bd112faca1e"

def main():
    namespace = {
        "__name__": __name__, "dataclass": dataclasses.dataclass,
        "field": dataclasses.field, "Literal": typing.Literal,
        "Mapping": typing.Mapping, "Path": Path, "urlsplit": urlsplit,
    }
    sources = {}
    for path, names in {
        "cascade/review.py": {"EpicCloseBlocker", "EpicReviewSnapshot", "validate_review_url", "persist_epic_review_snapshot"},
        "cascade/boss/epic_complete.py": {"_sync_receipt", "_persist_verified_epic_closure"},
    }.items():
        source = subprocess.check_output(["git", "show", f"{REVISION}:{path}"], text=True)
        sources[path] = hashlib.sha256(source.encode()).hexdigest()
        tree = ast.parse(source)
        nodes = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in names]
        assert len(nodes) == len(names)
        module = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes], type_ignores=[])
        exec(compile(ast.fix_missing_locations(module), path, "exec"), namespace)
    Snapshot = namespace["EpicReviewSnapshot"]
    current = Snapshot(stage="implementation_review_pending", review_url="https://example.test/pulls/2", source_branch="epic/new", target_branch="main", forge_state="merged", generation=2, observation_identity="new-observation", accepted_merge_sha="b" * 40, observed_target_sha="d" * 40, post_merge_ci={"state": "pending", "merge_sha": "b" * 40, "observed_target_sha": "d" * 40})
    writes = []
    namespace["epic_review_snapshot"] = lambda *args, **kwargs: current
    namespace["locate_trunk"] = lambda root: root
    namespace["_update_record"] = lambda root, key, changes, **kwargs: writes.append({"record": changes, "write_options": kwargs})
    sync = typing.NamedTuple("Sync", [(k, object) for k in ("ok", "target", "local_sha", "remote_sha", "sync_result", "board_fingerprint", "reason", "owner", "prerequisite")])(True, "main", "c" * 40, "c" * 40, "current", "old-board-proof", None, None, None)
    namespace["_persist_verified_epic_closure"]("epic_probe", Path("/unused"), {"accepted_merge_identity": {"merge_sha": "a" * 40, "observed_target_head": "c" * 40}, "post_merge_ci": {"state": "green", "merge_sha": "a" * 40, "observed_target_sha": "c" * 40}}, "old-board-proof", sync)
    assert len(writes) == 1
    row = writes[0]["record"]
    assert row["current_generation"] == 2 and row["observation_identity"] == "new-observation"
    assert row["accepted_merge_sha"] == "a" * 40 and row["verified_closure"] is True
    assert writes[0]["write_options"] == {"create": True}
    print(json.dumps({"revision": REVISION, "source_sha256": sources, "result": "stale proof adopts newer generation and sets verified_closure", "writes": writes, "limitation": "Extracted production functions/classes with in-memory reader/writer; no registry write, full caller scheduling or lifecycle-lock exclusion tested."}, indent=2))

if __name__ == "__main__":
    main()
