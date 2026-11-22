"""Read-only comparisons of committed planning work, independent of publication."""
from __future__ import annotations

import difflib
import os
import tempfile
import subprocess
from dataclasses import replace
from pathlib import Path

from cascade.board.errors import BoardError
from cascade.board.gitutil import path_for_work_id
from cascade.workspace.doc_root import read_doc_resolved
from cascade.workspace.integration_worktree import load_registry_readonly, locate_trunk

MAX_TEXT_BYTES = 2 * 1024 * 1024


def _git(root: Path, *args: str) -> str:
    try:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, timeout=10)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Planning comparison timed out reading Git") from exc
    if result.returncode:
        raise ValueError("Planning comparison revision is unavailable")
    if len(result.stdout) > MAX_TEXT_BYTES:
        raise ValueError("Planning comparison exceeds 2 MiB")
    return result.stdout.decode("utf-8")


def _blob(root: Path, revision: str, path: str | None) -> str:
    return _git(root, "show", f"{revision}:{path}") if path else ""


def _body(text: str) -> str:
    if text.startswith("---\n"):
        parts = text.split("\n---\n", 1)
        if len(parts) == 2:
            return parts[1].lstrip("\n")
    return text


def compare_document(path: str, before: str, after: str) -> dict:
    old, new = before.splitlines(), after.splitlines()
    removed, added = [], []
    for tag, a, b, c, d in difflib.SequenceMatcher(None, old, new, autojunk=False).get_opcodes():
        if tag != "equal":
            removed.extend(range(a + 1, b + 1))
            added.extend(range(c + 1, d + 1))
    return {"path": path, "current": before, "proposed": after,
            "removed_lines": removed, "added_lines": added,
            "changed": before != after}


def comparison_context(root: Path, work_id: str):
    doc = read_doc_resolved(work_id, root=root)
    trunk = locate_trunk(root)
    registry = load_registry_readonly(trunk)
    owner = next((row for row in registry if row.work_id == work_id), None)
    # Undispatched briefs belong to the nearest registered planning ancestor.
    parent = doc.meta.parent
    seen = {work_id}
    while owner is None and parent:
        if parent in seen:
            raise ValueError("Planning ownership contains a parent cycle")
        seen.add(parent)
        owner = next((row for row in registry if row.work_id == parent), None)
        parent = read_doc_resolved(parent, root=root).meta.parent
    if owner is None:
        raise ValueError("No registered planning branch is available yet")
    if _git(owner.path, "branch", "--show-current").strip() != owner.branch:
        raise ValueError("The planning checkout no longer matches its registered branch")
    revision = _git(owner.path, "rev-parse", "HEAD").strip()
    base = _git(owner.path, "rev-parse", f"{owner.base_sha}^{{commit}}").strip()
    _git(owner.path, "merge-base", "--is-ancestor", base, revision)
    return doc, owner, base, revision


def plan_comparison(root: Path, work_id: str) -> dict:
    """Compare the whole proposal against its registered base, never HEAD~1."""
    try:
        _doc, owner, base, revision = comparison_context(root, work_id)
        before_path = path_for_work_id(owner.path, base, work_id)
        after_path = path_for_work_id(owner.path, revision, work_id)
        if not after_path:
            raise ValueError("The proposed plan has not been committed yet")
        plans = compare_document(after_path, _body(_blob(owner.path, base, before_path)),
                                 _body(_blob(owner.path, revision, after_path)))
        paths = {}
        for side, rev in (("current", base), ("proposed", revision)):
            paths[side] = {p for p in _git(owner.path, "ls-tree", "-r", "--name-only", rev).splitlines()
                           if p == "DESIGN.md" or p.endswith("/DESIGN.md")}
        designs = []
        design_tree = []
        total = 0
        for path in sorted(paths["current"] | paths["proposed"]):
            before = _blob(owner.path, base, path) if path in paths["current"] else ""
            after = _blob(owner.path, revision, path) if path in paths["proposed"] else ""
            state = ("added" if path not in paths["current"] else
                     "removed" if path not in paths["proposed"] else
                     "changed" if before != after else "unchanged")
            design_tree.append({"path": path, "state": state})
            if state == "unchanged":
                continue
            total += len(before.encode()) + len(after.encode())
            if total > MAX_TEXT_BYTES:
                raise ValueError("Design comparison exceeds 2 MiB")
            designs.append({**compare_document(path, before, after), "state": state})
        return {"state": "draft", "owner_work_id": owner.work_id,
                "current_revision": base, "proposed_revision": revision,
                "message": "Committed branch preview · current is the branch base; proposed is the latest commit. Publication and approval are separate.",
                "plan": plans, "designs": designs, "design_tree": design_tree}
    except (ValueError, OSError, BoardError) as exc:
        return {"state": "unavailable", "message": str(exc), "designs": []}



def project_projection_revision(root: Path, current: str, proposal: str) -> str:
    """Preview integration in a private index/worktree; never move a real ref.

    A branch snapshot alone can omit work that already landed in the project.
    Git's normal three-way merge preserves that work and detects conflicts.
    The deterministic commit is an immutable renderer input, not an approval.
    """
    common = _git(root, "merge-base", current, proposal).strip()
    if common == current:
        return proposal
    if common == proposal:
        return current
    git_dir = Path(_git(root, "rev-parse", "--git-common-dir").strip())
    if not git_dir.is_absolute():
        git_dir = (root / git_dir).resolve()
    with tempfile.TemporaryDirectory(prefix="cascade-project-preview-") as directory:
        private = Path(directory)
        checkout = private / "worktree"
        checkout.mkdir()
        env = {**os.environ, "GIT_DIR": str(git_dir), "GIT_WORK_TREE": str(checkout),
               "GIT_INDEX_FILE": str(private / "index"), "GIT_OPTIONAL_LOCKS": "0",
               "GIT_AUTHOR_NAME": "Cascade architecture preview",
               "GIT_AUTHOR_EMAIL": "architecture-preview@localhost",
               "GIT_COMMITTER_NAME": "Cascade architecture preview",
               "GIT_COMMITTER_EMAIL": "architecture-preview@localhost",
               "GIT_AUTHOR_DATE": "2000-01-01T00:00:00+00:00",
               "GIT_COMMITTER_DATE": "2000-01-01T00:00:00+00:00"}

        def run(*args, input=None, check=True):
            try:
                result = subprocess.run(
                    ["git", "-c", "core.hooksPath=/dev/null", *args], cwd=checkout,
                    env=env, input=input, text=True, capture_output=True, timeout=30,
                )
            except subprocess.TimeoutExpired as exc:
                raise ValueError("Project architecture preview timed out during integration") from exc
            if check and result.returncode:
                raise ValueError("Unable to prepare the project architecture projection")
            return result

        run("read-tree", "--reset", "-u", current)
        merged = run("merge-recursive", common, "--", current, proposal, check=False)
        if merged.returncode:
            conflicts = run("diff", "--name-only", "--diff-filter=U").stdout.strip()
            raise ValueError("Proposal conflicts with the current project; reconcile before previewing: " +
                             (conflicts[:2000] or "integration could not be completed"))
        tree = run("write-tree").stdout.strip()
        return run("commit-tree", tree, "-p", current, "-p", proposal,
                   input=f"Project architecture preview\n\nCurrent: {current}\nProposal: {proposal}\n").stdout.strip()


def project_target_changes(diff) -> dict[str, str]:
    """Use the same change classification for both sides of a project target."""
    changes = {item.semantic_id: item.state for item in diff.identities}
    for item in diff.containment:
        changes[item.semantic_id] = "changed"
    for item in diff.identities:
        if item.previous_semantic_id:
            changes[item.previous_semantic_id] = changes[item.semantic_id]
    return changes


def comparison_metadata(artifact) -> dict[str, dict]:
    """Expose pinned semantic attributes for before/after inspection."""
    from cascade.workspace.c4_review import _read_semantic_workspace, _semantic_targets
    workspace = _read_semantic_workspace(artifact)
    identities = _semantic_targets(workspace)
    result = {}
    def visit(value, kind=None):
        if isinstance(value, list):
            for item in value:
                visit(item, kind)
        elif isinstance(value, dict):
            semantic_id = value.get('properties', {}).get('cascade.semanticId')
            if semantic_id in identities:
                result[semantic_id] = {
                    'type': {'people': 'Person', 'softwareSystems': 'Software system',
                             'containers': 'Container', 'components': 'Component',
                             'customElements': 'Code element', 'relationships': 'Relationship'}.get(kind, kind),
                    'description': value.get('description', ''),
                    'technology': value.get('technology', ''),
                    'tags': value.get('tags', ''), 'url': value.get('url', ''),
                    'parent': identities[semantic_id].parent,
                    'properties': {key: item for key, item in value.get('properties', {}).items()
                                   if not key.startswith('structurizr.')},
                }
            for key, child in value.items():
                if key != 'properties':
                    visit(child, key if isinstance(child, list) else kind)
    visit(workspace['model'])
    return result


def draft_diagrams(root: Path, work_id: str, *, scheduler=None, snapshot_ids=None) -> dict:
    """Explicit preview creation uses the bounded, cached browsing renderer."""
    from cascade.war_room.architecture_routes import project_for, _snapshot_projection, _authorized_snapshot
    from cascade.workspace.architecture_browsing import architecture_context_catalog
    from cascade.workspace.architecture_snapshots import ArchitectureSnapshotStore
    from cascade.workspace.c4_diff import compute_c4_semantic_diff

    _doc, owner, _branch_base, proposal_revision = comparison_context(root, work_id)
    project = project_for(root)
    current_revision = _git(project.target.root, "rev-parse", "HEAD").strip()
    if project.architecture_repository.root != project.target.root:
        raise ValueError("Draft diagrams require a published review for split architecture repositories")
    catalog = architecture_context_catalog(project, root)
    selected = next((s for s in catalog.contexts if s.context.work_id == owner.work_id), None)
    if selected is None:
        raise ValueError("The registered planning branch is not available for architecture browsing")
    current_selection = next(s for s in catalog.contexts if s.context.context_id == catalog.default_context_id)
    payload = {"state": "pending", "draft": True, "project_comparison": True, "owner_work_id": work_id,
               "review_unit_id": "", "reviewed_tuple_digest": "", "approval_context": None,
               "summary": "Project architecture: current integration state → expected state after the selected proposal.",
               "views": [], "changed_views": [], "resources": [], "diffs": {},
               "requirements": [], "decisions": [],
               "legend": [{"state": s, "meaning": m} for s, m in
                          [("added", "present only in proposed"), ("removed", "present only in current"),
                           ("changed", "semantic content changed"), ("unchanged", "no semantic change")]]}
    snapshots, projections, artifacts = {}, {}, {}
    with ArchitectureSnapshotStore(project, root, scheduler=scheduler) as store:
        if snapshot_ids:
            snapshots = {side: _authorized_snapshot(store, snapshot_ids[side])
                         for side in ("current", "proposed")}
            evidence = snapshots["proposed"].descriptor["association"].get("evidence_id", "")
            parts = evidence.split(":")
            if len(parts) != 3 or parts[0] != "project-preview":
                raise ValueError("Refresh to compare against the current project")
            pinned_current, pinned_proposal = parts[1:]
            for side, selection in (("current", current_selection), ("proposed", selected)):
                pinned = snapshots[side].descriptor
                if pinned["context"]["context_id"] != selection.context.context_id:
                    raise ValueError("Preview snapshot belongs to a different project or proposal")
                if pinned["association"].get("evidence_id") != evidence:
                    raise ValueError("Preview snapshot pair does not share an integration projection")
            if snapshots["current"].descriptor["revisions"]["code"] != pinned_current:
                raise ValueError("Preview current revision does not match its project evidence")
            _git(owner.path, "merge-base", "--is-ancestor", pinned_current, current_revision)
            _git(owner.path, "merge-base", "--is-ancestor", pinned_proposal, proposal_revision)
        else:
            pinned_current, pinned_proposal = current_revision, proposal_revision
            projected = project_projection_revision(project.target.root, pinned_current, pinned_proposal)
            evidence = f"project-preview:{pinned_current}:{pinned_proposal}"
            for side, rev, source in (("current", pinned_current, current_selection),
                                      ("proposed", projected, selected)):
                selection = replace(source, context=replace(source.context, revision=rev, dirty=False),
                                    mapping_revision=rev, documentation_revision=rev,
                                    documentation_ref_required=False, accepted_lineage=None,
                                    association_provenance="colocated", association_evidence_id=evidence)
                snapshots[side] = store.create_selection(selection)
        payload["project_revisions"] = {
            "current": pinned_current, "proposal_source": pinned_proposal,
            "projected": snapshots["proposed"].descriptor["revisions"]["code"],
            "current_branch": current_selection.context.branch,
        }
        payload["newer_revision_available"] = (
            pinned_current != current_revision or pinned_proposal != proposal_revision
        )
        payload["snapshot_ids"] = {side: snap.snapshot_id for side, snap in snapshots.items()}
        for side, snapshot in snapshots.items():
            if snapshot.state not in {"ready", "missing_model"}:
                payload["state"] = snapshot.state
                payload["summary"] = f"{side.title()} diagram: {snapshot.message or snapshot.state}"
                return payload
            if snapshot.state == "ready":
                projections[side] = _snapshot_projection(store, snapshot, cursor=0, limit=100)
                artifacts[side] = store.scheduler.get_semantic_artifact(
                    snapshot.render_operation_id, artifact_ref=snapshot.snapshot_id)
        base = snapshots["current"].descriptor["revisions"]["code"]
        revision = snapshots["proposed"].descriptor["revisions"]["code"]
        diff = compute_c4_semantic_diff(artifacts.get("current"), artifacts.get("proposed"),
                                       source_diff_reference=f"draft:{base}:{revision}")
        if diff.error:
            payload.update(state="invalid_artifact", summary=diff.error)
            return payload
        changes = project_target_changes(diff)
        metadata = {side: comparison_metadata(artifact) for side, artifact in artifacts.items()}
        view_changes = {item.key: item.state for item in diff.views}
        keyed = {side: {(v["key"], v["level"]): v for v in p["views"]}
                 for side, p in projections.items()}
        for key, level in sorted(set(keyed.get("current", {})) | set(keyed.get("proposed", {}))):
            view = {"key": key, "level": level, "state": view_changes.get(key, "unchanged")}
            for side, rev in (("current", base), ("proposed", revision)):
                item = keyed.get(side, {}).get((key, level))
                view[side] = None
                view[side + "_state"] = "present" if item else "absent"
                if item:
                    targets = [{**t, **metadata[side].get(t["semantic_id"], {}), "state": changes.get(t["semantic_id"], "unchanged")}
                               for t in projections[side]["targets"] if t["semantic_id"] in item["target_ids"]]
                    view[side] = {"repository_key": selected.context.repository_key,
                                  "revision": rev, "svg": item["artifact_url"], "targets": targets}
            payload["views"].append(view)
        levels = {name: i for i, name in enumerate((
            "systemLandscapeViews", "systemContextViews", "containerViews", "componentViews", "codeViews"
        ))}
        payload["views"].sort(key=lambda v: (levels.get(v["level"], 99), v["key"]))
        changed = sorted(
            (v for v in payload["views"] if v["state"] != "unchanged"),
            key=lambda v: (not bool(v["current"] and v["proposed"]), levels.get(v["level"], 99), v["key"]),
        )
        payload["changed_views"] = [[v["key"], v["level"]] for v in changed]
        payload["state"] = "ready" if payload["views"] else "missing_model"
        payload["summary"] += " " + diff.summary
        from cascade.workspace.c4_comparison import attach_comparison
        attach_comparison(payload, store.scheduler, renames={
            item.previous_semantic_id: item.semantic_id for item in diff.identities if item.previous_semantic_id
        })
        return payload
