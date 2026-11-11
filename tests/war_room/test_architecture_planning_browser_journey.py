"""Fresh planning-to-browser architecture review acceptance journey."""

from __future__ import annotations

import hashlib
import json
import shutil
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.agent.mcp_wrappers import ToolEffectCollector, dispatch_planning_tool
from cascade.board.context import set_project_context
from cascade.board.store import read_doc
from cascade.war_room.architecture_routes import (
    MAX_METADATA_BYTES,
    MAX_RESOURCE_BYTES,
    MAX_SVG_BYTES,
)
from cascade.war_room.server import serve
from cascade.workspace import (
    ArchitectureBaseline,
    ArchitectureModelBinding,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    C4ArtifactRenderer,
    C4RenderSettings,
    PinnedArchitectureArtifact,
    PinnedDocumentRef,
    ProjectContext,
    create_architecture_artifact_ref,
    create_architecture_model_ref,
    materialize_c4_source_closure,
    resolve_design_ownership,
)
from cascade.workspace.c4_render import STRUCTURIZR_IMAGE, STRUCTURIZR_IMAGE_DIGEST
from cascade.workspace.c4_scheduler import render_identity
from tests.support import add_doc, declare_no_dependencies, make_repo


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(root: Path, message: str, *paths: Path) -> str:
    _git(root, "add", *(path.relative_to(root).as_posix() for path in paths))
    _git(root, "commit", "-m", message)
    return _git(root, "rev-parse", "HEAD")


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _start(root: Path):
    server = serve(root=root, port=_free_port())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def _stop(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _get(url: str) -> bytes:
    with urllib.request.urlopen(url) as response:
        assert response.status == 200
        return response.read()


def _write_model(project: ProjectContext, feature_id: str, *, revised: bool) -> tuple[Path, ...]:
    architecture = project.editable_architecture_root
    architecture.mkdir(parents=True, exist_ok=True)
    contract = architecture / "workspace.contract.json"
    workspace = architecture / "workspace.dsl"
    model = architecture / "model.dsl"
    views = architecture / "views.dsl"
    contract.write_text(
        json.dumps(
            {
                "version": 1,
                "workspace": {"source": "workspace.dsl", "owner": feature_id},
                "fragments": [
                    {"path": "model.dsl", "owner": feature_id},
                    {"path": "views.dsl", "owner": feature_id},
                ],
                "elements": [
                    {
                        "dsl_identifier": "reviewer",
                        "semantic_id": "element.person.reviewer",
                        "fragment": "model.dsl",
                    },
                    {
                        "dsl_identifier": "portal",
                        "semantic_id": "element.system.portal",
                        "fragment": "model.dsl",
                    },
                ],
                "relationships": [
                    {
                        "dsl_identifier": "reviewer_uses_portal",
                        "semantic_id": "relationship.reviewer-uses-portal",
                        "source": "reviewer",
                        "destination": "portal",
                        "fragment": "model.dsl",
                    }
                ],
                "views": [{"key": "portal-context", "fragment": "views.dsl"}],
                "renames": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    workspace.write_text(
        'workspace "Review portal" "Planning browser journey" {\n'
        "  !impliedRelationships false\n"
        "  model {\n"
        "    !include model.dsl\n"
        "  }\n"
        "  views {\n"
        "    !include views.dsl\n"
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    description = (
        "Opens the immutable architecture review in the War Room."
        if revised
        else "Opens architecture reviews in the War Room."
    )
    model.write_text(
        'reviewer = person "Reviewer" "Reviews planned architecture." {\n'
        "  properties {\n"
        '    "cascade.semanticId" "element.person.reviewer"\n'
        "  }\n"
        "}\n"
        f'portal = softwareSystem "Review portal" "{description}" {{\n'
        "  properties {\n"
        '    "cascade.semanticId" "element.system.portal"\n'
        "  }\n"
        "}\n"
        'reviewer_uses_portal = reviewer -> portal "Reviews" {\n'
        "  properties {\n"
        '    "cascade.semanticId" "relationship.reviewer-uses-portal"\n'
        "  }\n"
        "}\n",
        encoding="utf-8",
    )
    views.write_text(
        'systemContext portal "portal-context" {\n'
        "  include *\n"
        "  autoLayout lr\n"
        "}\n",
        encoding="utf-8",
    )
    return contract, workspace, model, views


def _binding(project: ProjectContext, feature_id: str) -> ArchitectureModelBinding:
    contract_ref = create_architecture_model_ref(
        project, ".", "workspace.contract.json", owning_work=feature_id
    )
    source_refs = tuple(
        create_architecture_model_ref(project, ".", name, owning_work=feature_id)
        for name in ("workspace.dsl", "model.dsl", "views.dsl")
    )
    with tempfile.TemporaryDirectory(prefix="architecture-browser-binding-") as directory:
        closure = materialize_c4_source_closure(
            project, contract_ref, source_refs, Path(directory) / "source"
        )
        settings = C4RenderSettings()
        rendered = C4ArtifactRenderer(
            project.target.root / ".cascade" / "c4-render-cache"
        ).submit(closure, settings).wait(timeout=120)
    assert rendered.status == "ready", rendered
    assert rendered.semantic_workspace is not None
    semantic_digest = _digest(rendered.semantic_workspace)
    return ArchitectureModelBinding(
        contract=PinnedArchitectureArtifact(
            contract_ref, _digest(project.target.root / contract_ref.repository_path)
        ),
        sources=tuple(
            PinnedArchitectureArtifact(
                reference, _digest(project.target.root / reference.repository_path)
            )
            for reference in source_refs
        ),
        source_closure_digest=closure.digest,
        renderer_image_digest=STRUCTURIZR_IMAGE_DIGEST,
        renderer_settings=tuple(sorted(settings.cache_payload().items())),
        semantic_artifact_digest=semantic_digest,
        render_identity=render_identity(closure.digest, settings),
    )


def _proposal(
    project: ProjectContext,
    feature_id: str,
    model: ArchitectureModelBinding,
    baseline: ArchitectureBaseline,
    pointer_id: str | None,
    generation: int | None,
) -> ArchitectureReviewUnit:
    feature = read_doc(feature_id, root=project.target.root)
    assert feature.sha is not None
    plan_path = feature.meta.path.relative_to(project.target.root)
    design_ref = create_architecture_artifact_ref(
        project, ".", owning_work=feature_id
    )
    return ArchitectureReviewUnit(
        owner_work_id="caller-cannot-select-owner",
        authorized_owner="caller-cannot-select-actor",
        target_repository_key=project.target_repository_key,
        code_directory=Path("."),
        design_owner_directory=Path("."),
        code_repository_key=project.target.repository_key,
        integration_lineage="epic:epic_001",
        documentation_repository_key=project.target_repository_key,
        documentation_repository_role="target",
        documentation_destination_path=Path("."),
        proposed_ancestor_context=None,
        accepted_baseline=baseline,
        baseline_pointer_id=pointer_id,
        baseline_generation=generation,
        rollout_version=1,
        status="draft",
        plan=PinnedDocumentRef(
            project.target.repository_key,
            "target",
            plan_path,
            feature.sha,
            _digest(feature.meta.path),
        ),
        design=PinnedArchitectureArtifact(design_ref, _digest(project.target.root / "DESIGN.md")),
        proposed_model=model,
        requirement_citations=("REQ-ARCH-REVIEW",),
        decision_citations=("DEC-REAL-RENDERER",),
        view_citations=("portal-context",),
        affected_work_ids=(feature_id,),
        architecture_impact="diagram_change",
        impact_reason="The portal description changes in the reviewed system context.",
    )


def _publish(
    root: Path,
    feature_id: str,
    proposal: ArchitectureReviewUnit,
    generation: int | None,
) -> tuple[dict[str, object], tuple[str, ...]]:
    collector = ToolEffectCollector()
    arguments = {
        "proposal": proposal.to_dict(),
        "expected_plan_revision": proposal.plan.revision,
        "expected_generation": generation,
    }
    operation_ids: list[str] = []
    deadline = time.monotonic() + 20
    while True:
        result = dispatch_planning_tool(
            "feature",
            "publish_architecture_review",
            arguments,
            scope_id=feature_id,
            repo_root=root,
            collector=collector,
            role="feature_architect",
        )
        assert isinstance(result, dict)
        operation_ids.append(str(result["operation_id"]))
        if result["status"] != "pending":
            return result, tuple(operation_ids)
        assert time.monotonic() < deadline, result
        time.sleep(0.05)


def test_fresh_planning_publication_survives_restart_and_opens_real_pair_in_chromium(
    tmp_path: Path,
) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    if shutil.which("docker") is None:
        pytest.skip("Docker is required for the real Structurizr journey")
    inspected = subprocess.run(
        ["docker", "image", "inspect", STRUCTURIZR_IMAGE],
        capture_output=True,
        text=True,
    )
    if inspected.returncode:
        pytest.skip("the pinned Structurizr image is unavailable")
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"Chromium is unavailable: {exc}")

        root = make_repo(tmp_path)
        add_doc(root, id="epic_001", title="Architecture", tier="epic", status="active")
        declare_no_dependencies("epic_001", root=root)
        collector = ToolEffectCollector()
        feature_id = dispatch_planning_tool(
            "epic",
            "mint_feature",
            {"title": "Review portal", "body_stub": "Expose a real paired review."},
            scope_id="epic_001",
            repo_root=root,
            collector=collector,
            role="epic_manager",
        )
        assert isinstance(feature_id, str)
        project = ProjectContext.colocated(root)
        set_project_context(project)
        resolve_design_ownership(project, ".")
        design_path = root / "DESIGN.md"
        design_path.write_text("# Review portal design\n", encoding="utf-8")
        model_paths = _write_model(project, feature_id, revised=False)
        feature_path = read_doc(feature_id, root=root).meta.path
        ownership_path = project.design_ownership_path
        baseline_revision = _commit(
            root,
            "plan baseline architecture review",
            feature_path,
            root / "docs" / "epics" / "2_active" / next(
                path.name for path in (root / "docs" / "epics" / "2_active").glob("epic_001_*.md")
            ),
            design_path,
            ownership_path,
            *model_paths,
        )

        try:
            first = _proposal(
                project,
                feature_id,
                _binding(project, feature_id),
                ArchitectureBaseline.empty(),
                None,
                None,
            )
            first_result, first_requests = _publish(root, feature_id, first, None)
            assert first_result["status"] == "ready"
            assert len(set(first_requests)) == 1
            first_unit_id = str(first_result["review_unit_id"])
            store = ArchitectureReviewStore(project)
            first_unit = store.get(first_unit_id)
            assert first_unit is not None

            first_server, first_thread, first_base = _start(root)
            try:
                first_projection = json.loads(
                    _get(first_base + f"/api/architecture/reviews/{feature_id}")
                )
                assert first_projection["state"] == "empty_baseline"
                assert first_projection["views"][0]["current"] is None
                assert first_projection["views"][0]["proposed"]["revision"] == baseline_revision
            finally:
                _stop(first_server, first_thread)

            store.record_review(
                first_unit_id,
                reviewer="human",
                decision="reviewed",
                reviewed_at=datetime.now(timezone.utc).isoformat(),
            )
            store.approve_review_unit(first_unit_id)
            accepted = store.accept(
                first_unit_id,
                accepted_code_head=baseline_revision,
                accepted_documentation_head=baseline_revision,
                expected_generation=None,
            )

            planned = dispatch_planning_tool(
                "feature",
                "read_doc",
                {"work_id": feature_id},
                scope_id=feature_id,
                repo_root=root,
                collector=collector,
                role="feature_architect",
            )
            planned.body += "\nThe proposed portal copy is revision pinned.\n"
            dispatch_planning_tool(
                "feature",
                "write_doc",
                {"doc": planned},
                scope_id=feature_id,
                repo_root=root,
                collector=collector,
                role="feature_architect",
            )
            _write_model(project, feature_id, revised=True)
            proposed_revision = _commit(
                root,
                "plan proposed architecture review",
                feature_path,
                project.editable_architecture_root / "model.dsl",
            )
            second = _proposal(
                project,
                feature_id,
                _binding(project, feature_id),
                accepted.baseline,
                accepted.pointer_id,
                accepted.generation,
            )
            second_result, repeated_requests = _publish(
                root, feature_id, second, accepted.generation
            )
            assert second_result["status"] == "ready"
            assert len(set(repeated_requests)) == 1
            assert second_result["render_operation_id"] != first_result["render_operation_id"]

            ledger = json.loads(
                (root / ".cascade" / "c4-render-operations.json").read_text(encoding="utf-8")
            )
            for operation_id in (
                first_result["render_operation_id"],
                second_result["render_operation_id"],
            ):
                assert ledger["operations"][operation_id]["attempts"] == 1

            server, thread, base = _start(root)
            try:
                doc_before = _get(base + f"/api/doc/{feature_id}")
                projection_before = _get(base + f"/api/architecture/reviews/{feature_id}")
            finally:
                _stop(server, thread)
            restarted, restarted_thread, restarted_base = _start(root)
            try:
                assert json.loads(_get(restarted_base + f"/api/doc/{feature_id}")) == json.loads(doc_before)
                projection_raw = _get(
                    restarted_base + f"/api/architecture/reviews/{feature_id}"
                )
                projection = json.loads(projection_raw)
                assert projection == json.loads(projection_before)
                assert projection["state"] == "ready"
                assert projection["review_unit_id"] == second_result["review_unit_id"]
                assert projection["reviewed_tuple_digest"] == second_result["reviewed_tuple_digest"]
                assert len(projection_raw) < MAX_METADATA_BYTES

                sides = projection["views"][0]
                assert sides["current"]["revision"] == baseline_revision
                assert sides["proposed"]["revision"] == proposed_revision
                assert sides["state"] == "changed"
                assert projection["diffs"]["model"]["identities"]
                assert projection["views"][0]["proposed"]["targets"]

                for side_name in ("current", "proposed"):
                    svg = _get(restarted_base + sides[side_name]["svg"])
                    assert len(svg) < MAX_SVG_BYTES
                    assert b"data-cascade-semantic-id" in svg
                for resource in projection["resources"]:
                    body = _get(restarted_base + resource["url"])
                    assert len(body) < MAX_RESOURCE_BYTES
                    if not resource["kind"].endswith("_diff"):
                        assert body

                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                page.goto(
                    restarted_base + f"/plan/{feature_id}", wait_until="domcontentloaded"
                )
                page.locator("#plan-body:not([hidden])").wait_for()
                page.locator(".paired-c4-side-current .paired-c4-svg").wait_for(timeout=20_000)
                page.locator(".paired-c4-side-proposed .paired-c4-svg").wait_for()
                revisions = page.locator(".paired-c4-revision").all_text_contents()
                assert any(baseline_revision in value for value in revisions)
                assert any(proposed_revision in value for value in revisions)
                assert page.locator(
                    '[aria-label="element element.system.portal"]'
                ).count() == 2
                assert "portal-context" in page.locator(
                    ".paired-c4-view-select"
                ).input_value()
                page.locator(".paired-c4-diffs summary").click()
                diff_text = page.locator(".paired-c4-diff-list").inner_text()
                assert '"state": "changed"' in diff_text
                assert '"properties"' in diff_text
                assert proposed_revision in page.locator(
                    ".paired-c4-side-proposed .paired-c4-revision"
                ).inner_text()

                proposed_target = page.locator(
                    '.paired-c4-side-proposed [aria-label="element element.system.portal"]'
                )
                proposed_target.click()
                assert page.locator(".paired-c4-target-selected").count() == 2
                assert "element element.system.portal" in page.locator(
                    ".paired-c4-status"
                ).inner_text()

                current_target = page.locator(
                    '.paired-c4-side-current [aria-label="element element.system.portal"]'
                )
                current_target.focus()
                current_target.press("Enter")
                assert current_target.get_attribute("aria-pressed") == "true"

                proposed_svg = page.locator(".paired-c4-side-proposed .paired-c4-svg")
                fitted_view_box = proposed_svg.get_attribute("viewBox")
                page.locator(
                    '.paired-c4-side-proposed .semantic-c4-toolbar button',
                    has_text="Zoom in",
                ).click()
                assert proposed_svg.get_attribute("viewBox") != fitted_view_box
                page.locator(
                    '.paired-c4-side-proposed .semantic-c4-toolbar button',
                    has_text="Fit",
                ).click()
                assert proposed_svg.get_attribute("viewBox") == fitted_view_box

                relationship = page.locator(
                    '.paired-c4-side-proposed '
                    '[aria-label="relationship relationship.reviewer-uses-portal"]'
                )
                relationship.click()
                assert page.locator(
                    ".paired-c4-side-proposed .semantic-c4-relationship-details"
                ).count() >= 1

                page.set_viewport_size({"width": 700, "height": 1000})
                current_box = page.locator(".paired-c4-side-current").bounding_box()
                proposed_box = page.locator(".paired-c4-side-proposed").bounding_box()
                assert current_box is not None and proposed_box is not None
                assert proposed_box["y"] > current_box["y"] + current_box["height"] - 2
                page.close()
            finally:
                _stop(restarted, restarted_thread)
        finally:
            browser.close()
            set_project_context(None)
            from cascade.workspace import architecture_publication

            scheduler = architecture_publication._schedulers.pop(root.resolve(), None)
            if scheduler is not None:
                scheduler.close()
