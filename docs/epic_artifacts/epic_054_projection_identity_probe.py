"""Read-only function-boundary probe of pinned child source; not an API test."""

import ast
from dataclasses import dataclass, field
import json
import re
import subprocess
from typing import Any
from urllib.parse import urlsplit


REVISION = "fe28e6820d8a554b83090be2a55b889bbb39e2f7"


def main():
    namespace = dict(globals())
    for path, names in (
        ("cascade/review.py", {"EpicReviewSnapshot", "validate_review_url"}),
        (
            "cascade/war_room/serialize.py",
            {
                "epic_review_snapshot_to_dict",
                "_bounded_delivery_text",
                "_exact_delivery_text",
                "_delivery_payload_too_large",
            },
        ),
    ):
        source = subprocess.check_output(
            ["git", "show", f"{REVISION}:{path}"], text=True
        )
        nodes = [n for n in ast.parse(source).body if getattr(n, "name", "") in names]
        assert len(nodes) == len(names)
        module = ast.Module(
            body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *nodes],
            type_ignores=[],
        )
        exec(compile(ast.fix_missing_locations(module), f"{REVISION}:{path}", "exec"), namespace)

    sha = "a" * 40
    cases = {}
    for label, ci, sync in (
        ("complete", {"state": "green", "merge_sha": sha, "observed_target_sha": sha}, {"ok": True, "local_sha": sha, "remote_sha": sha}),
        ("missing_identities", {"state": "green"}, {"ok": True, "remote_sha": sha}),
        ("mismatched_local_sha", {"state": "green", "merge_sha": sha, "observed_target_sha": sha}, {"ok": True, "local_sha": "b" * 40, "remote_sha": sha}),
    ):
        snapshot = namespace["EpicReviewSnapshot"](
            stage="completed", forge_state="merged", generation=1,
            observation_identity="probe", accepted_merge_sha=sha,
            observed_target_sha=sha, post_merge_ci=ci, board_fingerprint="board-proof",
            sync_receipt=sync, verified_closure=True,
        )
        delivery = namespace["epic_review_snapshot_to_dict"](snapshot)["delivery"]
        cases[label] = {k: delivery[k] for k in ("merge_ci", "trunk_sync", "verified_closure")}
        assert delivery["verified_closure"]["verified"] is True
        assert delivery["merge_ci"]["state"] == "green"
        assert delivery["trunk_sync"]["state"] == "succeeded"
    print(json.dumps({
        "revision": REVISION,
        "result": "complete and both invalid identity cases display verified closure",
        "cases": cases,
        "limits": "Executes extracted production declarations with their decorators and helper functions; no registry, HTTP, browser or end-to-end writer reachability is tested.",
    }, indent=2))


if __name__ == "__main__":
    main()
