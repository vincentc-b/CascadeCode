"""Production HTTP coverage for scoped architecture review resources."""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import SimpleNamespace

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
from cascade.workspace.architecture_snapshots import ArchitectureBrowsingSnapshot
from cascade.workspace.types import ProjectContext
from cascade.workspace.c4_render import C4ArtifactRenderer, C4RenderArtifact
from cascade.workspace.c4_review import C4ReviewPayload
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


def _post(url: str, payload: dict[str, object]) -> tuple[int, bytes, dict[str, str]]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
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


def test_context_catalog_exposes_session_target_without_accepting_queries(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    root.joinpath("README.md").write_text("# Product\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "product"], cwd=root, check=True)
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    server, thread, base = _start(root)
    try:
        status, raw, headers = _get(base + "/api/architecture/contexts")
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        payload = json.loads(raw)
        assert payload["schema_version"] == 1
        context = payload["contexts"][0]["context"]
        assert payload["default_context_id"] == context["context_id"]
        assert context == {
            "context_id": payload["default_context_id"],
            "kind": "session_target",
            "label": "Session target",
            "repository_key": context["repository_key"],
            "revision": revision,
            "branch": "main",
            "detached": False,
            "dirty": False,
            "work_id": None,
        }
        assert payload["contexts"][0]["documentation_revision"] == revision
        assert payload["contexts"][0]["association"]["provenance"] == "colocated"

        status, raw, _headers = _get(base + "/api/architecture/contexts?path=/tmp")
        assert status == 400
        assert json.loads(raw)["error"] == (
            "architecture contexts do not accept query parameters"
        )
    finally:
        _stop(server, thread)


def test_snapshot_http_is_scoped_pinned_and_does_not_create_review_units(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    project = ProjectContext.colocated(root)
    resolve_design_ownership(project, ".")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "mapping only"], cwd=root, check=True)
    reviews = ArchitectureReviewStore(project)
    assert reviews.units_affecting("feat_001") == ()

    server, thread, base = _start(root)
    try:
        status, raw, headers = _post(base + "/api/architecture/snapshots", {})
        assert status == 200
        assert headers["Cache-Control"] == "no-store"
        snapshot = json.loads(raw)
        assert snapshot["state"] == "missing_model"
        assert snapshot["provenance"]["revisions"]["code"] == subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()
        assert snapshot["associated_review"] is None
        snapshot_id = snapshot["snapshot_id"]

        status, raw, _headers = _get(
            base + f"/api/architecture/snapshots/{snapshot_id}"
        )
        assert status == 200
        assert json.loads(raw)["snapshot_id"] == snapshot_id

        mapping = snapshot["resources"][0]
        status, body, resource_headers = _get(base + mapping["url"])
        assert status == 200
        assert json.loads(body)["version"] == 1
        assert resource_headers["Cache-Control"] == (
            "private, max-age=31536000, immutable"
        )
        etag_request = urllib.request.Request(
            base + mapping["url"], headers={"If-None-Match": resource_headers["ETag"]}
        )
        try:
            urllib.request.urlopen(etag_request)
        except urllib.error.HTTPError as exc:
            assert exc.code == 304

        forged = snapshot_id[:-1] + ("0" if snapshot_id[-1] != "0" else "1")
        status, raw, _headers = _get(
            base + f"/api/architecture/snapshots/{forged}"
        )
        assert status == 404
        assert json.loads(raw)["error"] == "architecture snapshot not found"

        root.joinpath("code.py").write_text("changed\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=root, check=True)
        subprocess.run(["git", "commit", "-qm", "advance"], cwd=root, check=True)
        status, raw, status_headers = _get(
            base + f"/api/architecture/snapshots/{snapshot_id}/status"
        )
        assert status == 200
        assert status_headers["Cache-Control"] == "no-store"
        assert json.loads(raw)["state"] == "changed"

        status, raw, _headers = _post(
            base + "/api/architecture/snapshots", {"context_id": "forged"}
        )
        assert status == 404
        assert "unknown_context" in json.loads(raw)["error"]
        assert reviews.units_affecting("feat_001") == ()
    finally:
        _stop(server, thread)


def test_ready_snapshot_exposes_validated_semantics_and_annotated_svg(
    tmp_path: Path, monkeypatch,
) -> None:
    root = make_repo(tmp_path)
    project = ProjectContext.colocated(root)
    resolve_design_ownership(project, ".")
    fixture = (
        Path(__file__).parents[2]
        / "architecture"
        / "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
    )
    shutil.copytree(fixture, project.editable_architecture_root)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "architecture"], cwd=root, check=True)

    class Result:
        def __init__(self, value: C4RenderArtifact) -> None:
            self.value = value

        def wait(self, timeout=None):  # type: ignore[no-untyped-def]
            return self.value

    def submit(_renderer, closure, settings=None):  # type: ignore[no-untyped-def]
        output = tmp_path / "rendered"
        output.mkdir(exist_ok=True)
        element = closure.contract.elements[0]
        view = closure.contract.views[0]
        workspace = {
            "model": {"softwareSystems": [{
                "id": "1", "name": "System",
                "properties": {"cascade.semanticId": element.semantic_id},
            }]},
            "views": {"systemContextViews": [{"key": view.key}]},
        }
        semantic = output / "workspace.json"
        semantic.write_text(json.dumps(workspace), encoding="utf-8")
        svg = output / "view.svg"
        svg.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg"><g id="node-1" '
            'data-cascade-model-kind="element" data-cascade-export-id="1" /></svg>',
            encoding="utf-8",
        )
        manifest = output / "hit-targets.json"
        manifest.write_text(json.dumps({
            "version": 1,
            "interactive": True,
            "source_diff_reference": "pinned:test",
            "views": [{
                "view_key": view.key,
                "svg": svg.name,
                "targets": [{
                    "view_key": view.key,
                    "renderer_node_id": "node-1",
                    "kind": "element",
                    "export_id": "1",
                    "semantic_id": element.semantic_id,
                }],
            }],
        }), encoding="utf-8")
        return Result(C4RenderArtifact(
            status="ready",
            closure_digest=closure.digest,
            artifact_directory=output,
            semantic_workspace=semantic,
            semantic_workspace_sha256=hashlib.sha256(semantic.read_bytes()).hexdigest(),
            svg_files=(svg,),
            binding_manifest=manifest,
            interactive=True,
            view_keys=(view.key,),
            revision=closure.revision,
        ))

    monkeypatch.setattr(C4ArtifactRenderer, "submit", submit)
    server, thread, base = _start(root)
    try:
        status, raw, _headers = _post(base + "/api/architecture/snapshots", {})
        assert status in {200, 202}
        payload = json.loads(raw)
        snapshot_id = payload["snapshot_id"]
        deadline = time.monotonic() + 3
        while payload["state"] == "pending" and time.monotonic() < deadline:
            status, raw, _headers = _get(
                base + f"/api/architecture/snapshots/{snapshot_id}"
            )
            assert status in {200, 202}
            payload = json.loads(raw)
            time.sleep(0.02)
        assert payload["state"] == "ready"
        assert payload["views"][0]["level"] == "systemContextViews"
        target = payload["targets"][0]
        assert target["semantic_id"]
        assert target["drill_choices"][0]["view_key"] == payload["views"][0]["key"]

        status, svg_body, headers = _get(base + payload["views"][0]["artifact_url"])
        assert status == 200
        assert b"data-cascade-semantic-id" in svg_body
        assert headers["ETag"].startswith('"')

        context_url = (
            base + f"/api/architecture/snapshots/{snapshot_id}/context"
            f"?view={payload['views'][0]['key']}"
            f"&level={payload['views'][0]['level']}"
        )
        status, raw, _headers = _get(context_url)
        assert status == 200
        context = json.loads(raw)
        assert context["scope_kind"] == "snapshot"
        assert context["scope_id"] == snapshot_id
        assert context["mapping_state"] == "unmapped"
        assert context["owner_context"][0]["source"]["revision"] == (
            payload["provenance"]["revisions"]["documentation"]
        )
        assert context["owner_context"][0]["document_url"].startswith(
            f"/api/architecture/resources/{snapshot_id}/"
        )

        status, raw, _headers = _get(
            base + f"/api/architecture/snapshots/{snapshot_id}?target=forged"
        )
        assert status == 400
        assert json.loads(raw)["error"] == "invalid semantic target"
    finally:
        _stop(server, thread)


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


def test_review_failure_gate_states_keep_plan_http_available(
    tmp_path: Path, monkeypatch,
) -> None:
    """Every non-ready review state remains explicit without hiding the plan.

    Backend tests exercise how these states arise.  This focused matrix pins the
    HTTP contract they share and guards the important failure boundary: a broken
    or incomplete architecture review must not make unrelated plan content
    unavailable.
    """
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "plan"], cwd=root, check=True)

    import cascade.war_room.architecture_routes as routes

    state = {"value": "pending"}
    reasons = {
        "empty_baseline": "validated proposal uses an explicit empty baseline",
        "no_diagram_change": "plan-only clarification is justified",
        "missing_review": "legacy plan has no immutable review unit",
        "pending": "renderer is still validating bounded evidence",
        "render_failed": "renderer failed without a static fallback",
        "invalid_artifact": "semantic SVG bindings are invalid",
        "stale_revision": "accepted baseline advanced",
        "missing_model": "pinned render artifact is missing",
        "partial_acceptance": "code landed while documentation remains pending",
    }

    def resolve(_root: Path, work_id: str) -> C4ReviewPayload:
        review_state = state["value"]
        reason = reasons[review_state]
        return C4ReviewPayload(
            state=review_state,
            owner_work_id=work_id,
            authorized_owner="epic_architect",
            review_unit_id="",
            reviewed_tuple_digest="",
            repositories=(),
            views=(),
            changed_views=(),
            legend=(),
            summary=reason,
            requirements=(),
            decisions=(),
            diffs={"source": None, "model": None, "plan": None},
            reason_code=review_state,
            reason=reason,
            error=(
                reason
                if review_state
                not in {"pending", "empty_baseline", "no_diagram_change"}
                else None
            ),
        )

    monkeypatch.setattr(routes, "_resolve", resolve)
    server, thread, base = _start(root)
    try:
        for review_state, reason in reasons.items():
            state["value"] = review_state
            status, raw, headers = _get(base + "/api/doc/epic_001")
            assert status == 200
            assert headers["Cache-Control"] == "no-store"
            document = json.loads(raw)
            assert document["meta"]["id"] == "epic_001"
            assert document["meta"]["title"] == "Epic"
            assert document["body"]
            assert document["paired_review"]["state"] == review_state
            assert document["paired_review"]["reason_code"] == review_state
            assert document["paired_review"]["message"] == reason

            status, raw, headers = _get(
                base + "/api/architecture/reviews/epic_001"
            )
            assert status == 200
            assert headers["Cache-Control"] == "no-store"
            projection = json.loads(raw)
            assert projection["state"] == review_state
            assert projection["reason"] == reason
            assert projection["views"] == []
            assert projection["resources"] == []
            assert projection["approval_context"] is None
    finally:
        _stop(server, thread)

    # An unexpected resolver failure is isolated to the review envelope.  The
    # plan and its other controls remain readable for unrelated work.
    monkeypatch.setattr(
        routes,
        "_resolve",
        lambda _root, _work_id: (_ for _ in ()).throw(RuntimeError("review store offline")),
    )
    server, thread, base = _start(root)
    try:
        status, raw, _headers = _get(base + "/api/doc/epic_001")
        assert status == 200
        document = json.loads(raw)
        assert document["meta"]["id"] == "epic_001"
        assert document["body"]
        assert document["paired_review"]["state"] == "unavailable"
        assert document["paired_review"]["message"] == "review store offline"
    finally:
        _stop(server, thread)


def test_opaque_resource_is_pinned_readable_bounded_and_tamper_safe(
    tmp_path: Path, monkeypatch,
) -> None:
    root = make_repo(tmp_path)
    project = ProjectContext.colocated(root)
    resolve_design_ownership(project, ".")
    plan_path = root / "docs" / "features" / "1_backlog" / "feat_001_plan.md"
    plan_path.write_text(
        "# Pinned plan\n\n"
        "- `REQ-PINNED-001` — Keep reads pinned.\n"
        "- `DEC-PINNED-001` — Use opaque resources.\n",
        encoding="utf-8",
    )
    design_path = root / "DESIGN.md"
    design_path.write_text(
        "# Pinned design\n\nThis is ownership context, not a decision source.\n",
        encoding="utf-8",
    )
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
        ("REQ-PINNED-001",), ("DEC-PINNED-001",), ("context",),
        ("feat_001",), "diagram_change", "Changes the model",
    )
    ArchitectureReviewStore(project).save(unit)
    descriptor = _resource_descriptors(unit)[0]
    resource_id = _opaque_id(descriptor)

    server, thread, base = _start(root)
    try:
        url = f"{base}/api/architecture/resources/{unit.review_unit_id}/{resource_id}"
        status, body, headers = _get(url)
        assert status == 200
        assert body == plan_path.read_bytes()
        assert headers["Content-Type"] == "text/markdown; charset=utf-8"
        assert headers["Cache-Control"] == "private, max-age=31536000, immutable"
        assert headers["ETag"].startswith('"')

        status, raw, _headers = _get(base + "/api/architecture/reviews/feat_001")
        assert status == 200
        projection = json.loads(raw)
        assert projection["approval_context"] == {
            "owner_work_id": "feat_001",
            "target_repository_key": project.target_repository_key,
            "plan_revision": revision,
            "review_unit_id": unit.review_unit_id,
            "reviewed_tuple_digest": unit.reviewed_tuple_digest,
            "accepted_baseline_generation": None,
        }
        plan_diff = next(
            row for row in projection["diffs"]["resources"]
            if row["kind"] == "plan_diff"
        )
        status, diff_body, diff_headers = _get(base + plan_diff["url"])
        assert status == 200
        assert diff_headers["Content-Type"] == "text/x-diff; charset=utf-8"
        assert b"+# Pinned plan" in diff_body

        # Context metadata validates against the selected review side, then
        # exposes only tuple-derived opaque URLs. No path or revision is
        # accepted from the request.
        import cascade.war_room.architecture_routes as routes

        side = SimpleNamespace(
            targets=(SimpleNamespace(
                semantic_id="element.api", kind="element"
            ),)
        )
        monkeypatch.setattr(
            routes,
            "_resolve_unit",
            lambda _root, _unit: SimpleNamespace(
                views=(SimpleNamespace(
                    key="context", level="systemContextViews",
                    proposed=side, current=None,
                ),)
            ),
        )
        context_url = (
            base + "/api/architecture/reviews/feat_001/context"
            "?side=proposed&view=context&level=systemContextViews"
            "&kind=element&target=element.api"
        )
        status, raw, _headers = _get(context_url)
        assert status == 200
        context = json.loads(raw)
        assert context["scope_id"] == unit.review_unit_id
        assert context["mapping_state"] == "unmapped"
        assert [row["document_id"] for row in context["view_links"]] == [
            "DEC-PINNED-001", "REQ-PINNED-001"
        ]
        requirement = next(
            row for row in context["view_links"]
            if row["document_id"] == "REQ-PINNED-001"
        )
        assert set(requirement["resources"]) == {"proposed_url", "section_url"}
        assert revision not in requirement["resources"]["section_url"]
        status, section, section_headers = _get(
            base + requirement["resources"]["section_url"]
        )
        assert status == 200
        assert section == b"- `REQ-PINNED-001` \xe2\x80\x94 Keep reads pinned.\n"
        assert section_headers["Content-Type"] == "text/markdown; charset=utf-8"

        decision = next(
            row for row in context["view_links"]
            if row["document_id"] == "DEC-PINNED-001"
        )
        assert decision["source"]["path"] == plan_path.relative_to(root).as_posix()
        status, section, _headers = _get(base + decision["resources"]["section_url"])
        assert status == 200
        assert section == b"- `DEC-PINNED-001` \xe2\x80\x94 Use opaque resources.\n"

        status, raw, _headers = _get(context_url.replace("element.api", "forged"))
        assert status == 400
        assert json.loads(raw)["error"] == "invalid documentation semantic target"

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


def test_documentation_ref_required_context_does_not_resolve_or_fetch(
    tmp_path: Path, monkeypatch,
) -> None:
    root = make_repo(tmp_path)
    project = ProjectContext.colocated(root)
    snapshot = ArchitectureBrowsingSnapshot(
        "architecture-snapshot-ref-required",
        "documentation_ref_required",
        {},
        reason_code="documentation_ref_required",
        message="select an exact known documentation revision",
    )

    import cascade.war_room.architecture_routes as routes

    class Store:
        def __init__(self, *_args, **_kwargs) -> None:
            self.project = project

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            pass

    monkeypatch.setattr(routes, "ArchitectureSnapshotStore", Store)
    monkeypatch.setattr(routes, "_authorized_snapshot", lambda *_args: snapshot)
    monkeypatch.setattr(
        routes,
        "snapshot_documentation_evidence",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("unpinned documentation evidence was resolved")
        ),
    )

    context = routes.snapshot_documentation_projection(
        root,
        snapshot.snapshot_id,
        view_key="unresolved",
        level="unresolved",
    )

    assert context == {
        "schema_version": 1,
        "scope_kind": "snapshot",
        "scope_id": snapshot.snapshot_id,
        "state": "documentation_ref_required",
        "documentation_ref_required": True,
        "reason": snapshot.message,
    }
