"""Production HTTP coverage for scoped architecture review resources."""

from __future__ import annotations

import hashlib
import json
import socket
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

from cascade.war_room.architecture_routes import _opaque_id, _resource_descriptors
from cascade.war_room.server import serve
from cascade.workspace.architecture import (
    create_architecture_artifact_ref,
    create_architecture_model_ref,
    resolve_design_ownership,
)
from cascade.workspace.architecture_review import (
    ArchitectureBaseline,
    ArchitectureModelBinding,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    PinnedArchitectureArtifact,
    PinnedDocumentRef,
)
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(url: str) -> tuple[int, bytes, dict[str, str]]:
    try:
        with urllib.request.urlopen(url) as response:
            return response.status, response.read(), dict(response.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), dict(exc.headers)


def _start(root: Path):
    server = serve(root=root, port=_free_port())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def _stop(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_doc_always_exposes_small_envelope_and_lazy_missing_projection(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "plan"], cwd=root, check=True)
    server, thread, base = _start(root)
    try:
        status, raw, headers = _get(base + "/api/doc/epic_001")
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        doc = json.loads(raw)
        envelope = doc["paired_review"]
        assert envelope == {
            "schema_version": 1,
            "resource_url": "/api/architecture/reviews/epic_001",
            "state": "missing_review",
            "reason_code": "missing_review",
            "message": "no architecture review is published for this owner and integration lineage",
            "review_unit_id": None,
            "reviewed_tuple_digest": None,
            "retry": {"retryable": False, "retry_after_seconds": None},
        }

        status, raw, _headers = _get(base + envelope["resource_url"])
        assert status == 200
        projection = json.loads(raw)
        assert projection["state"] == "missing_review"
        assert projection["views"] == []
        assert projection["resources"] == []
        assert projection["pagination"]["total"] == 0

        status, raw, _headers = _get(
            base + "/api/architecture/reviews/epic_001?cursor=bad"
        )
        assert status == 400
        assert json.loads(raw)["error"] == "invalid review pagination"
    finally:
        _stop(server, thread)


def test_opaque_resource_is_pinned_readable_bounded_and_tamper_safe(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    project = ProjectContext.colocated(root)
    resolve_design_ownership(project, ".")
    plan_path = root / "docs" / "features" / "1_backlog" / "feat_001_plan.md"
    plan_path.write_text("# Pinned plan\n", encoding="utf-8")
    design_path = root / "DESIGN.md"
    design_path.write_text("# Pinned design\n", encoding="utf-8")
    architecture = project.editable_architecture_root
    architecture.mkdir(parents=True, exist_ok=True)
    contract_path = architecture / "workspace.contract.json"
    contract_path.write_text('{"version":1}\n', encoding="utf-8")
    source_path = architecture / "model.dsl"
    source_path.write_text("workspace {}\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "pinned inputs"], cwd=root, check=True)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()

    def digest(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    plan = PinnedDocumentRef(
        project.target.repository_key, "target", plan_path.relative_to(root),
        revision, digest(plan_path),
    )
    design = PinnedArchitectureArtifact(
        create_architecture_artifact_ref(project, ".", owning_work="feat_001"),
        digest(design_path),
    )
    model = ArchitectureModelBinding(
        PinnedArchitectureArtifact(
            create_architecture_model_ref(
                project, ".", "workspace.contract.json", owning_work="feat_001"
            ), digest(contract_path),
        ),
        (PinnedArchitectureArtifact(
            create_architecture_model_ref(project, ".", "model.dsl", owning_work="feat_001"),
            digest(source_path),
        ),),
        "2" * 64, "3" * 64, (), "4" * 64,
    )
    unit = ArchitectureReviewUnit(
        "feat_001", "feature_architect", project.target_repository_key,
        Path("."), Path("."), project.target.repository_key, "epic:epic_001",
        project.target_repository_key, "target", Path("."), None,
        ArchitectureBaseline.empty(), None, None, 1, "staged", plan, design, model,
        (), (), (), ("feat_001",), "diagram_change", "Changes the model",
    )
    ArchitectureReviewStore(project).save(unit)
    descriptor = _resource_descriptors(unit)[0]
    resource_id = _opaque_id(descriptor)

    server, thread, base = _start(root)
    try:
        url = f"{base}/api/architecture/resources/{unit.review_unit_id}/{resource_id}"
        status, body, headers = _get(url)
        assert status == 200
        assert body == b"# Pinned plan\n"
        assert headers["Content-Type"] == "text/markdown; charset=utf-8"
        assert headers["Cache-Control"] == "private, max-age=31536000, immutable"
        assert headers["ETag"].startswith('"')

        status, raw, _headers = _get(base + "/api/architecture/reviews/feat_001")
        assert status == 200
        projection = json.loads(raw)
        plan_diff = next(
            row for row in projection["diffs"]["resources"]
            if row["kind"] == "plan_diff"
        )
        status, diff_body, diff_headers = _get(base + plan_diff["url"])
        assert status == 200
        assert diff_headers["Content-Type"] == "text/x-diff; charset=utf-8"
        assert b"+# Pinned plan" in diff_body

        status, raw, _headers = _get(url[:-1] + ("0" if url[-1] != "0" else "1"))
        assert status == 404
        assert json.loads(raw)["error"] == "architecture resource not found"

        status, raw, _headers = _get(
            f"{base}/api/architecture/resources/not-{unit.review_unit_id}/{resource_id}"
        )
        assert status == 404
        assert json.loads(raw)["error"] == "architecture scope not found"
    finally:
        _stop(server, thread)
