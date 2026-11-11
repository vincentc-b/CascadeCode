"""Real renderer and Chromium acceptance for commit-pinned branch browsing."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import threading
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from cascade.board.context import set_project_context
from cascade.war_room.architecture_routes import context_catalog
from cascade.war_room.server import serve
from cascade.workspace import (
    ArchitectureBaseline,
    ArchitectureModelBinding,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    PinnedArchitectureArtifact,
    PinnedDocumentRef,
    ProjectContext,
    STRUCTURIZR_IMAGE,
    C4RenderSettings,
    create_architecture_artifact_ref,
    create_architecture_model_ref,
    resolve_design_ownership,
)
from cascade.workspace.integration_worktree import IntegrationWorktree, save_registry
from tests.support import make_repo


ROOT = Path(__file__).resolve().parents[2]
VERSIONED_MODEL = ROOT / "architecture" / "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
JOURNEY_VIEWS = """systemContext cascade "cascade-context" {
    include *
    autoLayout lr
}

container cascade "cascade-containers" {
    include *
    autoLayout lr
}
"""
JOURNEY_MODEL = """operator = person "Operator" "Reviews branch architecture." {
    properties {
        "cascade.semanticId" "element.person.operator"
    }
}

cascade = softwareSystem "Cascade" "Coordinates artifact-driven delivery in a Git repository." {
    properties {
        "cascade.semanticId" "element.system.cascade"
    }

    war_room = container "War Room" "Presents pinned architecture." "Python HTTP" {
        properties {
            "cascade.semanticId" "element.container.war-room"
        }
    }
    supervisor = container "Service" "Coordinates delivery." "Python" {
        properties {
            "cascade.semanticId" "element.container.supervisor"
        }
    }
}

operator_uses_war_room = operator -> war_room "Uses" {
    properties {
        "cascade.semanticId" "relationship.operator-uses-war-room"
    }
}
war_room_calls_supervisor = war_room -> supervisor "Invokes" {
    properties {
        "cascade.semanticId" "relationship.war-room-calls-supervisor"
    }
}
"""


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _commit(root: Path, message: str) -> str:
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", message], cwd=root, check=True)
    return _git(root, "rev-parse", "HEAD")


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _start(root: Path):
    server = serve(root=root, port=_free_port())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread, f"http://127.0.0.1:{server.server_port}"


def _stop(server, thread: threading.Thread) -> None:  # type: ignore[no-untyped-def]
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def _request_json(url: str, payload: dict[str, object] | None = None):
    request = urllib.request.Request(
        url,
        data=(json.dumps(payload).encode() if payload is not None else None),
        headers=({"Content-Type": "application/json"} if payload is not None else {}),
        method=("POST" if payload is not None else "GET"),
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _install_model(root: Path, *, system_name: str | None = None) -> ProjectContext:
    project = ProjectContext.colocated(root)
    resolve_design_ownership(project, ".")
    shutil.copytree(VERSIONED_MODEL, project.editable_architecture_root)
    _limit_model_views(project.editable_architecture_root)
    if system_name is not None:
        model = project.editable_architecture_root / "model.dsl"
        model.write_text(
            model.read_text(encoding="utf-8").replace(
                'cascade = softwareSystem "Cascade"',
                f'cascade = softwareSystem "{system_name}"',
            ),
            encoding="utf-8",
        )
    return project


def _limit_model_views(architecture: Path) -> None:
    """Keep the proof bounded to the semantic model and views it browses."""

    architecture.joinpath("model.dsl").write_text(JOURNEY_MODEL, encoding="utf-8")
    architecture.joinpath("views.dsl").write_text(JOURNEY_VIEWS, encoding="utf-8")
    contract_path = architecture / "workspace.contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    semantic_ids = {
        "element.person.operator",
        "element.system.cascade",
        "element.container.war-room",
        "element.container.supervisor",
    }
    relationship_ids = {
        "relationship.operator-uses-war-room",
        "relationship.war-room-calls-supervisor",
    }
    contract["elements"] = [
        element
        for element in contract["elements"]
        if element["semantic_id"] in semantic_ids
    ]
    contract["relationships"] = [
        relationship
        for relationship in contract["relationships"]
        if relationship["semantic_id"] in relationship_ids
    ]
    contract["views"] = [
        view
        for view in contract["views"]
        if view["key"] in {"cascade-context", "cascade-containers"}
    ]
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _add_worktree(root: Path, work_id: str, base: str) -> Path:
    worktree = root / ".cascade" / "worktrees" / f"feat_{work_id}"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "worktree", "add", "-qb", f"feat/{work_id}", str(worktree), base],
        cwd=root,
        check=True,
    )
    return worktree


def _record_context_review(
    store_project: ProjectContext, branch: Path, revision: str
) -> ArchitectureReviewUnit:
    """Attach reviewed citations to the exact branch snapshot used by Chromium."""

    project = ProjectContext.colocated(branch)
    contract = create_architecture_model_ref(
        project, ".", "workspace.contract.json", owning_work="feat_branch"
    )
    sources = tuple(
        create_architecture_model_ref(
            project, ".", name, owning_work="feat_branch"
        )
        for name in ("workspace.dsl", "model.dsl", "views.dsl")
    )
    binding = ArchitectureModelBinding(
        PinnedArchitectureArtifact(
            contract, _digest(branch / contract.repository_path)
        ),
        tuple(
            PinnedArchitectureArtifact(
                source, _digest(branch / source.repository_path)
            )
            for source in sources
        ),
        "1" * 64,
        "2" * 64,
        (),
        "3" * 64,
        "4" * 64,
    )
    plan_path = Path("FEATURE.md")
    design = create_architecture_artifact_ref(
        project, ".", owning_work="feat_branch"
    )
    unit = ArchitectureReviewUnit(
        "feat_branch",
        "feature_architect",
        project.target_repository_key,
        Path("."),
        Path("."),
        store_project.target.repository_key,
        "epic:epic_browser",
        project.target_repository_key,
        "target",
        Path("."),
        None,
        ArchitectureBaseline.empty(),
        None,
        None,
        1,
        "reviewed",
        PinnedDocumentRef(
            store_project.target.repository_key,
            "target",
            plan_path,
            revision,
            _digest(branch / plan_path),
        ),
        PinnedArchitectureArtifact(design, _digest(branch / design.repository_path)),
        binding,
        ("REQ-BRANCH-CONTEXT",),
        ("DEC-BRANCH-PIN",),
        ("cascade-context", "cascade-containers"),
        ("feat_branch",),
        "diagram_change",
        "The branch snapshot carries its exact reviewed documentation context.",
    )
    ArchitectureReviewStore(store_project).save(unit)
    return unit


def _record_split_review(
    project: ProjectContext, code_revision: str, documentation_revision: str
) -> tuple[ArchitectureReviewUnit, str]:
    """Record the real durable code/docs association consumed by browsing."""

    docs = project.architecture_repository.root
    contract = create_architecture_model_ref(
        project, ".", "workspace.contract.json", owning_work="feat_split"
    )
    sources = tuple(
        create_architecture_model_ref(project, ".", name, owning_work="feat_split")
        for name in ("workspace.dsl", "model.dsl", "views.dsl")
    )
    binding = ArchitectureModelBinding(
        PinnedArchitectureArtifact(contract, _digest(docs / contract.repository_path)),
        tuple(
            PinnedArchitectureArtifact(source, _digest(docs / source.repository_path))
            for source in sources
        ),
        "1" * 64,
        "2" * 64,
        (),
        "3" * 64,
        "4" * 64,
    )
    plan_path = Path("FEATURE.md")
    design = create_architecture_artifact_ref(project, ".", owning_work="feat_split")
    unit = ArchitectureReviewUnit(
        "feat_split",
        "feature_architect",
        project.target_repository_key,
        Path("."),
        Path("."),
        project.target.repository_key,
        "epic:epic_split",
        project.architecture_repository.repository_key,
        "tracking",
        Path("."),
        None,
        ArchitectureBaseline.empty(),
        None,
        None,
        1,
        "reviewed",
        PinnedDocumentRef(
            project.architecture_repository.repository_key,
            "tracking",
            plan_path,
            documentation_revision,
            _digest(docs / plan_path),
        ),
        PinnedArchitectureArtifact(design, _digest(docs / design.repository_path)),
        binding,
        ("REQ-SPLIT-PIN",),
        ("DEC-SPLIT-ASSOCIATION",),
        ("cascade-context",),
        ("feat_split",),
        "diagram_change",
        "The accepted lineage binds distinct code and documentation commits.",
    )
    store = ArchitectureReviewStore(project)
    store.save(unit)
    accepted = store.accept(
        unit.review_unit_id,
        accepted_code_head=code_revision,
        accepted_documentation_head=documentation_revision,
        expected_generation=None,
    )
    return unit, accepted.pointer_id


def _evidence_dir() -> Path | None:
    value = os.environ.get("CASCADE_BRANCH_BROWSER_EVIDENCE_DIR")
    if not value:
        return None
    destination = Path(value).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    return destination


def _capture(page, name: str) -> None:  # type: ignore[no-untyped-def]
    destination = _evidence_dir()
    if destination is not None:
        page.screenshot(path=destination / name, full_page=True)


def _record_evidence(name: str, payload: dict[str, object]) -> None:
    destination = _evidence_dir()
    if destination is not None:
        (destination / name).write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )


def _wait_for_snapshot(page, *, timeout: int = 240_000) -> None:  # type: ignore[no-untyped-def]
    page.locator("#architecture-ready:not([hidden])").wait_for(timeout=timeout)
    page.locator("#architecture-viewer .semantic-c4-svg").wait_for(timeout=20_000)


def _select_context(page, label: str) -> None:  # type: ignore[no-untyped-def]
    select = page.locator("#architecture-context")
    options = select.locator("option")
    index = next(
        i for i, value in enumerate(options.all_text_contents()) if label in value
    )
    value = options.nth(index).get_attribute("value")
    assert value
    select.select_option(value=value)


@pytest.fixture
def real_browser():
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
        try:
            yield browser
        finally:
            browser.close()


def test_branch_architecture_is_pinned_navigable_and_refreshes_whole_snapshot(
    tmp_path: Path, real_browser,
) -> None:
    root = make_repo(tmp_path)
    root.joinpath(".gitignore").write_text(".cascade/\n", encoding="utf-8")
    root.joinpath("FEATURE.md").write_text(
        "# Branch architecture\n\n"
        "- `REQ-BRANCH-CONTEXT` — Keep architecture context pinned.\n"
        "- `DEC-BRANCH-PIN` — Never substitute tracking HEAD.\n",
        encoding="utf-8",
    )
    root.joinpath("DESIGN.md").write_text(
        "# Browser architecture design\n",
        encoding="utf-8",
    )
    main_project = _install_model(root)
    main_revision = _commit(root, "main architecture")

    branch = _add_worktree(root, "feat_branch", main_revision)
    branch_model = ProjectContext.colocated(branch).editable_architecture_root / "model.dsl"
    branch_model.write_text(
        branch_model.read_text(encoding="utf-8").replace(
            'softwareSystem "Cascade"', 'softwareSystem "Branch Atlas"', 1
        ),
        encoding="utf-8",
    )
    branch.joinpath("FEATURE.md").write_text(
        "# Branch architecture\n\n"
        "- `REQ-BRANCH-CONTEXT` — Open context from this branch revision.\n"
        "- `DEC-BRANCH-PIN` — Never substitute tracking HEAD.\n",
        encoding="utf-8",
    )
    branch_revision = _commit(branch, "different branch architecture")
    branch_review = _record_context_review(main_project, branch, branch_revision)

    detached = _add_worktree(root, "feat_detached", main_revision)
    subprocess.run(["git", "checkout", "--detach", main_revision], cwd=detached, check=True)
    detached_model = ProjectContext.colocated(detached).editable_architecture_root / "model.dsl"
    detached_model.write_text(
        detached_model.read_text(encoding="utf-8").replace(
            'softwareSystem "Cascade"', 'softwareSystem "DIRTY SECRET"', 1
        ),
        encoding="utf-8",
    )

    missing = _add_worktree(root, "feat_missing", main_revision)
    shutil.rmtree(ProjectContext.colocated(missing).editable_architecture_root)
    missing_revision = _commit(missing, "remove branch architecture")

    broken = _add_worktree(root, "feat_broken", main_revision)
    broken_model = ProjectContext.colocated(broken).editable_architecture_root / "model.dsl"
    broken_model.write_text(
        broken_model.read_text(encoding="utf-8") + "\nthis is not structurizr dsl !!!\n",
        encoding="utf-8",
    )
    broken_revision = _commit(broken, "broken branch architecture")

    save_registry(root, [
        IntegrationWorktree("feature", "feat_branch", "feat/feat_branch", branch, main_revision),
        IntegrationWorktree("feature", "feat_detached", "feat/feat_detached", detached, main_revision),
        IntegrationWorktree("feature", "feat_missing", "feat/feat_missing", missing, main_revision),
        IntegrationWorktree("feature", "feat_broken", "feat/feat_broken", broken, main_revision),
    ])

    server, thread, base = _start(root)
    try:
        page = real_browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(base + "/?tab=architecture", wait_until="domcontentloaded")
        _wait_for_snapshot(page)

        # The session checkout is the default and all provenance is readable.
        assert page.locator("#architecture-context").input_value()
        provenance = page.locator("#architecture-provenance-list").inner_text()
        assert "Session target" in provenance
        assert "main" in provenance
        assert main_revision in provenance
        source_links = page.locator("#architecture-source-list a")
        assert source_links.count() >= 4
        source_url = source_links.filter(has_text="model.dsl").get_attribute("href")
        assert source_url
        with urllib.request.urlopen(base + source_url) as response:
            assert b'softwareSystem "Cascade"' in response.read()

        view = page.locator("#architecture-view")
        labels = view.locator("option").all_text_contents()
        context_index = next(i for i, value in enumerate(labels) if "cascade-context" in value)
        view.select_option(index=context_index)
        cascade = page.locator('[aria-label="element element.system.cascade"]')
        cascade.click()
        assert "Cascade" in page.locator("#architecture-target-detail").inner_text()

        # Drill/back plus the real shared viewer's fit, zoom, and pan controls.
        cascade = page.locator('[aria-label="element element.system.cascade"]')
        cascade.dispatch_event("dblclick")
        page.locator("#architecture-drill-choices button", has_text="cascade-containers").click()
        assert "cascade-containers" in view.input_value()
        relationship = page.locator(
            '[aria-label="relationship relationship.operator-uses-war-room"]'
        )
        relationship.click()
        details = page.locator("#architecture-target-detail").inner_text()
        assert "Relationship" in details and "→" in details
        page.locator("#architecture-back").click()
        assert "cascade-containers" in view.input_value()
        page.locator("#architecture-back").click()
        assert "cascade-context" in view.input_value()
        svg = page.locator("#architecture-viewer .semantic-c4-svg")
        fitted = svg.get_attribute("viewBox")
        page.locator("#architecture-viewer button", has_text="Zoom in").click()
        assert svg.get_attribute("viewBox") != fitted
        page.locator("#architecture-viewer button", has_text="Fit").click()
        assert svg.get_attribute("viewBox") == fitted
        page.evaluate(
            """() => {
              const svg = document.querySelector('#architecture-viewer svg');
              svg.dispatchEvent(new PointerEvent('pointerdown', {bubbles: true,
                button: 0, pointerId: 7, clientX: 5, clientY: 5}));
              svg.dispatchEvent(new PointerEvent('pointermove', {bubbles: true,
                button: 0, pointerId: 7, clientX: 45, clientY: 25}));
              svg.dispatchEvent(new PointerEvent('pointerup', {bubbles: true,
                button: 0, pointerId: 7, clientX: 45, clientY: 25}));
            }"""
        )
        assert svg.get_attribute("viewBox") != fitted
        page.locator("#architecture-viewer button", has_text="Fit").click()

        # Selection is encoded in the deep link and restored from the same pin.
        cascade = page.locator('[aria-label="element element.system.cascade"]')
        cascade.click()
        deep_link = page.url
        assert "snapshot=architecture-snapshot-" in deep_link
        assert "target=element.system.cascade" in deep_link
        page.reload(wait_until="domcontentloaded")
        _wait_for_snapshot(page, timeout=30_000)
        assert page.locator(
            '[aria-label="element element.system.cascade"]'
        ).get_attribute("aria-pressed") == "true"

        # A distinct known branch stays responsive while its real render runs.
        _select_context(page, "feat_branch")
        page.locator("#war-room-board-tab").click()
        assert page.locator("#war-room-board-panel").is_visible()
        page.locator("#war-room-architecture-tab").click()
        page.wait_for_function(
            "revision => document.querySelector('#architecture-provenance-list').textContent.includes(revision)",
            arg=branch_revision,
            timeout=240_000,
        )
        _wait_for_snapshot(page)
        branch_snapshot = re.search(r"snapshot=([^&]+)", page.url)
        assert branch_snapshot
        status, branch_payload = _request_json(
            base + f"/api/architecture/snapshots/{branch_snapshot.group(1)}"
        )
        assert status == 200
        assert branch_payload["associated_review"]["review_unit_id"] == (
            branch_review.review_unit_id
        )
        assert "Branch Atlas" in page.locator(
            '[aria-label="element element.system.cascade"]'
        ).get_attribute("aria-description")
        _capture(page, "branch-browsing.png")

        # The Architecture tab resolves the same two reviewed documents for
        # both cited views, and opens source/full Markdown only on demand.
        view = page.locator("#architecture-view")
        context_index = next(
            index
            for index, label in enumerate(view.locator("option").all_text_contents())
            if "cascade-context" in label
        )
        view.select_option(index=context_index)
        requirement = page.locator(
            ".architecture-context-row", has_text="REQ-BRANCH-CONTEXT"
        )
        requirement.wait_for()
        assert page.locator(
            ".architecture-context-row", has_text="DEC-BRANCH-PIN"
        ).count() == 1
        assert branch_revision in requirement.inner_text()
        requirement.locator("button", has_text="Open source section").click()
        page.locator(
            "#architecture-document-preview-body",
            has_text="Open context from this branch revision",
        ).wait_for()
        requirement.locator("button", has_text="Open full document").click()
        preview = page.locator("#architecture-document-preview-body")
        preview.filter(has_text="Never substitute tracking HEAD").wait_for()
        assert "Branch architecture" in preview.inner_text()

        container_index = next(
            index
            for index, label in enumerate(view.locator("option").all_text_contents())
            if "cascade-containers" in label
        )
        view.select_option(index=container_index)
        page.locator(
            ".architecture-context-row", has_text="REQ-BRANCH-CONTEXT"
        ).wait_for()
        assert page.locator(
            ".architecture-context-row", has_text="DEC-BRANCH-PIN"
        ).count() == 1
        view.select_option(index=context_index)
        cascade = page.locator('[aria-label="element element.system.cascade"]')
        cascade.click()
        page.locator(
            "#architecture-documentation-content",
            has_text="Unmapped target",
        ).wait_for()
        documentation_text = page.locator(
            "#architecture-documentation-content"
        ).inner_text()
        assert "Ownership context only" in documentation_text
        explicit_group = page.locator(".architecture-context-group").filter(
            has=page.locator("h4", has_text="Explicit target links")
        )
        assert "REQ-BRANCH-CONTEXT" not in explicit_group.inner_text()
        assert "REQ-BRANCH-CONTEXT" in documentation_text
        assert "Links for the enclosing view" in documentation_text

        pinned_snapshot = re.search(r"snapshot=([^&]+)", page.url)
        assert pinned_snapshot
        old_snapshot_id = pinned_snapshot.group(1)
        old_source_url = page.locator(
            "#architecture-source-list a", has_text="model.dsl"
        ).get_attribute("href")
        assert old_source_url

        # Board refreshes do not admit more rendering work for an open snapshot.
        ledger_path = root / ".cascade" / "c4-render-operations.json"
        operation_count = len(json.loads(ledger_path.read_text())["operations"])
        page.evaluate(
            """async () => { for (let i = 0; i < 3; i += 1) {
              const response = await fetch('/api/board'); if (!response.ok) throw Error(response.status);
            }}"""
        )
        assert len(json.loads(ledger_path.read_text())["operations"]) == operation_count

        branch_model.write_text(
            branch_model.read_text(encoding="utf-8").replace(
                "Coordinates artifact-driven delivery", "Coordinates refreshed delivery"
            ),
            encoding="utf-8",
        )
        refreshed_revision = _commit(branch, "advance branch head")
        status, head = _request_json(
            base + f"/api/architecture/snapshots/{old_snapshot_id}/status"
        )
        assert status == 200
        assert head["schema_version"] == 1
        assert head["snapshot_id"] == old_snapshot_id
        assert head["state"] == "changed"
        assert head["changed"] is True
        assert head["pinned_revision"] == branch_revision
        assert head["current_revision"] == refreshed_revision
        assert branch_revision in page.locator("#architecture-provenance-list").inner_text()
        with urllib.request.urlopen(base + old_source_url) as response:
            assert b"Coordinates artifact-driven delivery" in response.read()
        page.locator("#architecture-update-indicator").wait_for(timeout=20_000)
        page.locator("#architecture-refresh-snapshot").click()
        page.wait_for_function(
            "revision => document.querySelector('#architecture-provenance-list').textContent.includes(revision)",
            arg=refreshed_revision,
            timeout=240_000,
        )
        _wait_for_snapshot(page)
        assert old_snapshot_id not in page.url
        assert page.locator(
            ".architecture-context-row", has_text="REQ-BRANCH-CONTEXT"
        ).count() == 0
        assert refreshed_revision in page.locator(
            "#architecture-documentation-content"
        ).inner_text()

        # Detached/dirty metadata is honest and dirty model bytes never leak.
        _select_context(page, "feat_detached")
        page.wait_for_function(
            "() => document.querySelector('#architecture-provenance-list').textContent.includes('Detached HEAD')",
            timeout=30_000,
        )
        _wait_for_snapshot(page)
        detached_provenance = page.locator("#architecture-provenance-list").inner_text()
        assert "Detached HEAD" in detached_provenance
        assert "Dirty (uncommitted edits excluded)" in detached_provenance
        detached_source = page.locator(
            "#architecture-source-list a", has_text="model.dsl"
        ).get_attribute("href")
        assert detached_source
        with urllib.request.urlopen(base + detached_source) as response:
            body = response.read()
        assert b'DIRTY SECRET' not in body
        assert b'softwareSystem "Cascade"' in body
        _capture(page, "detached-dirty.png")

        # Missing content and a genuine renderer failure remain explicit.
        _select_context(page, "feat_missing")
        page.locator("#architecture-status").filter(
            has_text="No versioned architecture model"
        ).wait_for(timeout=10_000)
        assert missing_revision in page.locator("#architecture-provenance-list").inner_text()
        _capture(page, "missing-model.png")

        _select_context(page, "feat_broken")
        page.locator("#architecture-status").filter(
            has_text="could not be rendered"
        ).wait_for(timeout=240_000)
        assert broken_revision in page.locator("#architecture-provenance-list").inner_text()
        assert page.locator("#war-room-architecture-tab").is_enabled()
        _record_evidence(
            "colocated-revisions.json",
            {
                "main_revision": main_revision,
                "branch_revision": branch_revision,
                "refreshed_branch_revision": refreshed_revision,
                "detached_revision": main_revision,
                "missing_model_revision": missing_revision,
                "broken_model_revision": broken_revision,
                "branch_review_unit_id": branch_review.review_unit_id,
                "initial_branch_snapshot_id": old_snapshot_id,
                "structurizr_image": STRUCTURIZR_IMAGE,
                "renderer_settings": C4RenderSettings().cache_payload(),
            },
        )

        # Snapshot/resource identifiers are the authorization boundary.
        forged = old_snapshot_id[:-1] + ("0" if old_snapshot_id[-1] != "0" else "1")
        assert _request_json(base + f"/api/architecture/snapshots/{forged}")[0] == 404
        forged_resource = old_source_url.rsplit("/", 1)[0] + "/not-authorized"
        try:
            urllib.request.urlopen(base + forged_resource)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError("forged architecture resource was readable")
        page.close()
    finally:
        _stop(server, thread)
        # Keep the global renderer cache assertion tied to the configured root.
        assert main_project.target.root == root


def test_split_repository_requires_and_applies_an_explicit_documentation_ref(
    tmp_path: Path, real_browser,
) -> None:
    target = make_repo(tmp_path / "target")
    tracking = make_repo(tmp_path / "tracking")
    target.joinpath(".gitignore").write_text(".cascade/\n", encoding="utf-8")
    project = ProjectContext.split(
        target, tracking, architecture_destination="tracking"
    )
    resolve_design_ownership(project, ".")
    target.joinpath("code.txt").write_text("accepted code\n", encoding="utf-8")
    code_revision = _commit(target, "code and architecture mapping")
    shutil.copytree(VERSIONED_MODEL, project.editable_architecture_root)
    _limit_model_views(project.editable_architecture_root)
    tracking.joinpath("FEATURE.md").write_text(
        "# Split architecture\n\n"
        "- `REQ-SPLIT-PIN` — Bind code to reviewed documentation.\n"
        "- `DEC-SPLIT-ASSOCIATION` — Never infer tracking HEAD.\n",
        encoding="utf-8",
    )
    project.design_path().parent.mkdir(parents=True, exist_ok=True)
    project.design_path().write_text("# Split architecture design\n", encoding="utf-8")
    documentation_revision = _commit(tracking, "split architecture model")
    review, accepted_pointer_id = _record_split_review(
        project, code_revision, documentation_revision
    )
    set_project_context(project)
    try:
        exact = context_catalog(target)["contexts"][0]
        assert exact["documentation_revision"] == documentation_revision
        assert exact["association"] == {
            "provenance": "accepted_lineage",
            "evidence_id": accepted_pointer_id,
        }
        server, thread, base = _start(target)
        try:
            page = real_browser.new_page(viewport={"width": 1200, "height": 900})
            page.goto(base + "/?tab=architecture", wait_until="domcontentloaded")
            _wait_for_snapshot(page)
            exact_provenance = page.locator("#architecture-provenance-list").inner_text()
            assert code_revision in exact_provenance
            assert documentation_revision in exact_provenance
            assert "accepted_lineage" in exact_provenance
            assert accepted_pointer_id in exact_provenance
            assert "Cascade" in page.locator(
                '[aria-label="element element.system.cascade"]'
            ).get_attribute("aria-description")
            _capture(page, "split-exact-association.png")

            # A real code HEAD update has no recorded association. A fresh
            # route load must not infer the distinct tracking HEAD.
            target.joinpath("code.txt").write_text(
                "accepted code\nunassociated code update\n", encoding="utf-8"
            )
            unassociated_code_revision = _commit(target, "unassociated code head")
            assert unassociated_code_revision != code_revision
            assert _git(tracking, "rev-parse", "HEAD") == documentation_revision
            page.goto(base + "/?tab=architecture", wait_until="domcontentloaded")
            choice = page.locator("#architecture-documentation-choice")
            choice.wait_for(timeout=10_000)
            assert "tracking HEAD will not be guessed" in page.locator(
                "#architecture-status"
            ).inner_text()
            _capture(page, "split-absent-association.png")
            refs = page.locator("#architecture-documentation-ref")
            assert documentation_revision in " ".join(
                refs.locator("option").all_text_contents()
            )
            refs.select_option(index=1)
            selected_ref = refs.input_value()
            assert selected_ref.startswith("documentation-")
            page.locator("#architecture-use-documentation-ref").click()
            _wait_for_snapshot(page)
            provenance = page.locator("#architecture-provenance-list").inner_text()
            assert unassociated_code_revision in provenance
            assert documentation_revision in provenance
            assert "user_selected" in provenance
            assert selected_ref in provenance
            _capture(page, "split-explicit-selection.png")
            _record_evidence(
                "split-revisions.json",
                {
                    "associated_code_revision": code_revision,
                    "unassociated_code_revision": unassociated_code_revision,
                    "documentation_revision": documentation_revision,
                    "review_unit_id": review.review_unit_id,
                    "accepted_pointer_id": accepted_pointer_id,
                    "selected_documentation_ref_id": selected_ref,
                    "structurizr_image": STRUCTURIZR_IMAGE,
                    "renderer_settings": C4RenderSettings().cache_payload(),
                },
            )
            page.close()
        finally:
            _stop(server, thread)
    finally:
        set_project_context(None)
