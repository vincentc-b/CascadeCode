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
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.agent.mcp_wrappers import ToolEffectCollector, dispatch_planning_tool
from cascade.board.context import set_project_context
from cascade.board.store import read_doc, write_doc
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
    enable_review_gate,
    create_architecture_artifact_ref,
    create_architecture_model_ref,
    materialize_c4_source_closure,
    resolve_design_ownership,
)
from cascade.workspace.c4_render import STRUCTURIZR_IMAGE, STRUCTURIZR_IMAGE_DIGEST
from cascade.workspace.c4_scheduler import render_identity
from tests.support import add_doc, declare_no_dependencies, make_repo
from tests.test_approval_selection_gate import _inventory


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
                    {
                        "dsl_identifier": "api",
                        "semantic_id": "element.container.api",
                        "fragment": "model.dsl",
                    },
                    *(
                        [{
                            "dsl_identifier": "audit",
                            "semantic_id": "element.container.audit",
                            "fragment": "model.dsl",
                        }]
                        if revised else []
                    ),
                ],
                "relationships": [
                    {
                        "dsl_identifier": "reviewer_uses_portal",
                        "semantic_id": "relationship.reviewer-uses-portal",
                        "source": "reviewer",
                        "destination": "portal",
                        "fragment": "model.dsl",
                    },
                    *(
                        [{
                            "dsl_identifier": "api_records_audit",
                            "semantic_id": "relationship.api-records-audit",
                            "source": "api",
                            "destination": "audit",
                            "fragment": "model.dsl",
                        }]
                        if revised else []
                    ),
                ],
                "views": [
                    {"key": "portal-context", "fragment": "views.dsl"},
                    {"key": "portal-containers", "fragment": "views.dsl"},
                ],
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
        '  api = container "Review API" "Serves pinned reviews." {\n'
        "    properties {\n"
        '      "cascade.semanticId" "element.container.api"\n'
        "    }\n"
        "  }\n"
        + (
            '  audit = container "Audit log" "Records review decisions." {\n'
            "    properties {\n"
            '      "cascade.semanticId" "element.container.audit"\n'
            "    }\n"
            "  }\n"
            if revised else ""
        )
        + "  properties {\n"
        '    "cascade.semanticId" "element.system.portal"\n'
        "  }\n"
        "}\n"
        'reviewer_uses_portal = reviewer -> portal "Reviews" {\n'
        "  properties {\n"
        '    "cascade.semanticId" "relationship.reviewer-uses-portal"\n'
        "  }\n"
        "}\n"
        + (
            'api_records_audit = api -> audit "Records" {\n'
            "  properties {\n"
            '    "cascade.semanticId" "relationship.api-records-audit"\n'
            "  }\n"
            "}\n"
            if revised else ""
        ),
        encoding="utf-8",
    )
    views.write_text(
        'systemContext portal "portal-context" {\n'
        "  include *\n"
        "  autoLayout lr\n"
        "}\n"
        'container portal "portal-containers" {\n'
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
        view_citations=("portal-context", "portal-containers"),
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
    monkeypatch: pytest.MonkeyPatch,
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
        feature = read_doc(feature_id, root=root)
        feature.meta.provider = "codex"
        feature.meta.models = {
            role: "offered" for role in ("feature_lead", "feature_architect", "swe")
        }
        feature.body += (
            "\n## Verified architecture context\n\n"
            "- `REQ-ARCH-REVIEW` — Reviewers can open revision-pinned evidence.\n"
            "- `DEC-REAL-RENDERER` — Use the real renderer for browser acceptance.\n"
        )
        write_doc(feature, root=root)
        monkeypatch.setattr(
            "cascade.approvals.get_provider_inventory", lambda: _inventory("offered")
        )
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
            planned.body = planned.body.replace(
                "Reviewers can open revision-pinned evidence.",
                "Reviewers can open current, proposed, and diff evidence.",
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
                *model_paths,
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
            second_unit_id = str(second_result["review_unit_id"])
            store.record_review(
                second_unit_id,
                reviewer="human",
                decision="reviewed",
                reviewed_at=datetime.now(timezone.utc).isoformat(),
            )
            enable_review_gate(project, version=1, store=store)

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
                assert len(projection["changed_views"]) == 2
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
                view_select = page.locator(".paired-c4-view-select")
                context_index = next(
                    index
                    for index, label in enumerate(
                        view_select.locator("option").all_text_contents()
                    )
                    if label.startswith("portal-context ")
                )
                view_select.select_option(index=context_index)
                assert "portal-context" in view_select.input_value()
                page.locator(".paired-c4-diffs summary").click()
                diff_text = page.locator(".paired-c4-diff-list").inner_text()
                assert '"state": "changed"' in diff_text
                assert '"properties"' in diff_text
                assert proposed_revision in page.locator(
                    ".paired-c4-side-proposed .paired-c4-revision"
                ).inner_text()

                # Context stays lazy until requested, then exposes both cited
                # documents for each cited view from the exact reviewed tuple.
                assert page.locator(".paired-c4-context-document").count() == 0
                page.locator(".paired-c4-context-toggle").click()
                page.locator(
                    '.paired-c4-context-document[data-document-id="REQ-ARCH-REVIEW"]'
                ).wait_for()
                context_documents = page.locator(".paired-c4-context-document")
                assert context_documents.count() == 2
                requirement_card = page.locator(
                    '.paired-c4-context-document[data-document-id="REQ-ARCH-REVIEW"]'
                )
                assert second.plan.revision in requirement_card.locator(
                    ".paired-c4-context-source"
                ).inner_text()
                requirement_card.locator(
                    ".paired-c4-context-preview"
                ).click()
                requirement_card.locator(
                    ".paired-c4-context-markdown",
                    has_text="current, proposed, and diff evidence",
                ).wait_for()
                resources = {
                    link.inner_text(): link.get_attribute("href")
                    for link in requirement_card.locator(
                        ".paired-c4-context-link"
                    ).all()
                }
                assert {
                    "Open source section",
                    "Open current document",
                    "Open proposed document",
                    "Open current/proposed diff",
                } <= resources.keys()
                assert b"Reviewers can open revision-pinned evidence" in _get(
                    restarted_base + resources["Open current document"]
                )
                assert b"current, proposed, and diff evidence" in _get(
                    restarted_base + resources["Open proposed document"]
                )
                assert b"- `REQ-ARCH-REVIEW` \xe2\x80\x94 Reviewers can open revision-pinned evidence" in _get(
                    restarted_base + resources["Open current/proposed diff"]
                )

                page.locator(
                    ".paired-c4-context-side", has_text="current"
                ).click()
                current_requirement = page.locator(
                    '.paired-c4-context-document[data-document-id="REQ-ARCH-REVIEW"]'
                )
                current_requirement.locator(
                    ".paired-c4-context-source", has_text=first.plan.revision
                ).wait_for()
                page.locator(
                    ".paired-c4-context-side", has_text="proposed"
                ).click()

                # The same requirement and decision are linked to both review
                # views: a browser-level many-to-many example.
                page.locator(".paired-c4-view-select").select_option(
                    index=next(
                        index
                        for index, label in enumerate(
                            page.locator(
                                ".paired-c4-view-select option"
                            ).all_text_contents()
                        )
                        if label.startswith("portal-containers ")
                    )
                )
                page.locator(
                    '.paired-c4-context-document[data-document-id="DEC-REAL-RENDERER"]'
                ).wait_for()
                assert page.locator(".paired-c4-context-document").count() == 2
                page.locator(".paired-c4-view-select").select_option(index=context_index)

                proposed_target = page.locator(
                    '.paired-c4-side-proposed [aria-label="element element.system.portal"]'
                )
                proposed_target.click()
                page.locator(".paired-c4-target-selected").first.wait_for()
                assert page.locator(".paired-c4-target-selected").count() == 2
                assert "element element.system.portal" in page.locator(
                    ".paired-c4-status"
                ).inner_text()
                page.locator(
                    ".paired-c4-context-unmapped",
                    has_text="Unmapped target",
                ).wait_for()
                assert "context, not coverage" in page.locator(
                    ".paired-c4-context"
                ).inner_text()

                current_target = page.locator(
                    '.paired-c4-side-current [aria-label="element element.system.portal"]'
                )
                current_target.focus()
                current_target.press("Enter")
                assert current_target.get_attribute("aria-pressed") == "true"

                # A system target has verified descendants in the container view,
                # so native double-click offers deterministic drill destinations.
                # Dispatch the native double-click without Playwright's leading
                # click pair: the first click intentionally rebuilds both SVGs.
                current_target.dispatch_event("dblclick")
                page.locator(
                    ".paired-c4-drill-choice", has_text="portal-containers"
                ).click()
                assert "portal-containers" in page.locator(
                    ".paired-c4-view-select"
                ).input_value()
                page.locator(".paired-c4-back").click()
                assert "portal-context" in page.locator(
                    ".paired-c4-view-select"
                ).input_value()
                container_index = next(
                    index
                    for index, label in enumerate(
                        page.locator(".paired-c4-view-select option").all_text_contents()
                    )
                    if label.startswith("portal-containers ")
                )
                page.locator(".paired-c4-view-select").select_option(index=container_index)
                assert page.locator(
                    '.paired-c4-side-proposed '
                    '[aria-label="element element.container.audit"]'
                ).get_attribute("data-cascade-diff-state") == "added"
                page.locator(
                    '.paired-c4-side-proposed '
                    '[aria-label="element element.container.audit"]'
                ).click()
                assert "current: absent, proposed: present" in page.locator(
                    ".paired-c4-status"
                ).inner_text()
                page.locator(".paired-c4-view-select").select_option(index=context_index)

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
                page.set_viewport_size({"width": 1440, "height": 1000})

                def post_thread(shortcut: str, body: str, *, blocking: bool = False) -> None:
                    page.locator(
                        ".paired-c4-comment-target", has_text=shortcut
                    ).click()
                    page.locator(".paired-c4-thread-body").fill(body)
                    if blocking:
                        page.locator(
                            '.paired-c4-thread-blocking input[type="checkbox"]'
                        ).check()
                    page.locator(".paired-c4-thread-send").click()
                    page.wait_for_function(
                        """body => Array.from(document.querySelectorAll(
                          '.paired-c4-thread-body-text')).some(node =>
                          node.textContent.includes(body)) ||
                          !!document.querySelector('.paired-c4-thread-error')""",
                            arg=body,
                    )
                    error = page.locator(".paired-c4-thread-error")
                    assert error.count() == 0, error.inner_text() if error.count() else ""

                post_thread(
                    "Comment on REQ-ARCH-REVIEW (proposed)",
                    "Requirement evidence is pinned.",
                )
                post_thread("Comment on proposed view", "View composition is reviewed.")
                proposed_target = page.locator(
                    '.paired-c4-side-proposed '
                    '[aria-label="element element.system.portal"]'
                )
                proposed_target.click()
                post_thread(
                    "Comment on selected element",
                    "Blocking portal decision.",
                    blocking=True,
                )
                page.locator(
                    '.paired-c4-side-proposed '
                    '[aria-label="relationship relationship.reviewer-uses-portal"]'
                ).click()
                post_thread(
                    "Comment on selected relationship",
                    "Relationship direction is intentional.",
                )
                assert page.locator(".paired-c4-thread").count() == 4

                requirement_thread = page.locator(
                    ".paired-c4-thread", has_text="Requirement evidence is pinned."
                )
                requirement_thread.locator(
                    ".paired-c4-thread-reply-body-input"
                ).fill("Reviewer reply from the live page.")
                requirement_thread.locator(".paired-c4-thread-reply-send").click()
                requirement_thread.locator(
                    ".paired-c4-thread-reply-body",
                    has_text="Reviewer reply from the live page.",
                ).wait_for()
                requirement_id = requirement_thread.get_attribute("data-thread-id")
                assert requirement_id
                incoming = page.evaluate(
                    """async ([docId, parent]) => {
                      const response = await fetch('/api/comment', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({doc_id: docId, parent,
                          body: 'Incoming reply from another reviewer.'})
                      });
                      return {status: response.status, body: await response.json()};
                    }""",
                    [feature_id, requirement_id],
                )
                assert incoming["status"] == 202
                page.reload(wait_until="domcontentloaded")
                page.locator("#plan-body:not([hidden])").wait_for()
                page.locator(
                    ".paired-c4-thread-reply-body",
                    has_text="Incoming reply from another reviewer.",
                ).wait_for(timeout=20_000)

                approval_context = projection["approval_context"]
                blocked_approval = page.evaluate(
                    """async ([id, review_context]) => {
                      const response = await fetch('/api/approve_feature', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({id, review_context})
                      });
                      return {status: response.status, body: await response.json()};
                    }""",
                    [feature_id, approval_context],
                )
                assert blocked_approval["status"] == 409
                assert "Blocking portal decision" not in json.dumps(blocked_approval)
                assert "blocking review thread" in blocked_approval["body"]["error"]

                blocking_thread = page.locator(
                    ".paired-c4-thread", has_text="Blocking portal decision."
                )
                blocking_thread.locator(".paired-c4-thread-resolve").click()
                blocking_thread = page.locator(
                    ".paired-c4-thread", has_text="Blocking portal decision."
                )
                blocking_thread.locator(".paired-c4-thread-reopen").click()
                blocking_thread = page.locator(
                    ".paired-c4-thread", has_text="Blocking portal decision."
                )
                blocking_thread.locator(".paired-c4-thread-resolve").click()
                page.locator(
                    ".paired-c4-thread", has_text="Blocking portal decision."
                ).locator(".paired-c4-thread-reopen").wait_for()

                stale_context = dict(approval_context)
                stale_context["reviewed_tuple_digest"] = "0" * 64
                stale_approval = page.evaluate(
                    """async ([id, review_context]) => {
                      const response = await fetch('/api/approve_feature', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({id, review_context})
                      });
                      return {status: response.status, body: await response.json()};
                    }""",
                    [feature_id, stale_context],
                )
                assert stale_approval["status"] == 409
                assert "displayed architecture review tuple" in stale_approval["body"]["error"]
                approved = page.evaluate(
                    """async ([id, review_context]) => {
                      const response = await fetch('/api/approve_feature', {
                        method: 'POST', headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({id, review_context})
                      });
                      return {status: response.status, body: await response.json()};
                    }""",
                    [feature_id, approval_context],
                )
                assert approved["status"] == 200
                assert approved["body"]["newly_approved"] is True
                assert "resolved" in page.locator(
                    ".paired-c4-thread", has_text="Blocking portal decision."
                ).locator(".paired-c4-thread-state").inner_text()

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
