"""Derived, single-canvas comparison graphs from authorized semantic projections.

These are presentation artifacts, never proposed models or acceptance evidence.
The ordinary confined Structurizr scheduler renders and binds their SVGs.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import replace
from pathlib import Path

from cascade.workspace.c4_closure import C4SourceClosure, C4SourceFile
from cascade.workspace.c4_source import validate_c4_workspace
from cascade.workspace.c4_review import _semantic_svg


def comparison_targets(view: dict, renames: dict[str, str] | None = None) -> list[dict]:
    """Union identities, retaining both connection variants when endpoints change."""
    renames = renames or {}
    sides = {}
    for side in ("current", "proposed"):
        sides[side] = {
            (t["kind"], renames.get(t["semantic_id"], t["semantic_id"])): t
            for t in (view.get(side) or {}).get("targets", [])
        }
    result = []
    for key in sorted(sides["current"].keys() | sides["proposed"].keys()):
        before, after = sides["current"].get(key), sides["proposed"].get(key)
        chosen = after or before
        state = (
            "added"
            if before is None
            else "removed"
            if after is None
            else "changed"
            if before.get("state") == "changed" or after.get("state") == "changed"
            else "unchanged"
        )
        target = {
            **chosen,
            "semantic_id": key[1],
            "state": state,
            "source_side": "proposed" if after else "current",
            "selection_id": chosen["semantic_id"],
            "before": before,
            "after": after,
        }
        for endpoint in ("source", "destination"):
            if target.get(endpoint):
                target[endpoint] = renames.get(target[endpoint], target[endpoint])
        if (
            before
            and after
            and key[0] == "relationship"
            and any(
                renames.get(before.get(e), before.get(e))
                != renames.get(after.get(e), after.get(e))
                for e in ("source", "destination")
            )
        ):
            # The old connection is a separate visible edge, with a derived ID.
            old_id = (
                "comparison.previous." + hashlib.sha256(key[1].encode()).hexdigest()
            )
            if ("relationship", old_id) in sides["current"] or (
                "relationship",
                old_id,
            ) in sides["proposed"]:
                raise ValueError("Combined relationship identity is ambiguous")
            previous = {
                **target,
                **before,
                "semantic_id": old_id,
                "state": "removed",
                "source_side": "current",
                "selection_id": before["semantic_id"],
                "before": before,
                "after": after,
            }
            for endpoint in ("source", "destination"):
                previous[endpoint] = renames.get(
                    before.get(endpoint), before.get(endpoint)
                )
            result.append(previous)
            target["state"] = "added"
        result.append(target)
    return result


def _quote(value: object) -> str:
    # Keep all data inside one DSL string, including literal quotes/newlines.
    return json.dumps(str(value or ""), ensure_ascii=False)


def comparison_source(
    views: list[dict],
    directory: Path,
    *,
    owner: str,
    evidence: str,
    repository_key: str,
) -> C4SourceClosure:
    """Materialize a bounded custom-view projection with reversible target bindings.

    A fresh layout places the union once. Custom shapes avoid inventing a real
    containment hierarchy when the revisions disagree about ownership.
    """
    if sum(len(view["combined_targets"]) for view in views) > 5000 or len(views) > 100:
        raise ValueError("Combined diagram exceeds the comparison size limit")
    # Equivalent displayed graphs share geometry, but retain per-view navigation,
    # diff states and before/after metadata. Do not merge merely similar graphs.
    representatives = {}
    layout_views = {}
    fields = (
        "kind",
        "semantic_id",
        "label",
        "type",
        "description",
        "source",
        "destination",
    )
    for index, view in enumerate(views):
        signature = json.dumps(
            [
                [target.get(field) for field in fields]
                for target in sorted(
                    view["combined_targets"],
                    key=lambda target: (target["kind"], target["semantic_id"]),
                )
            ],
            sort_keys=True,
        )
        layout_views[index] = representatives.setdefault(signature, index)
    targets = {}
    for index, view in enumerate(views):
        if layout_views[index] != index:
            continue
        for target in view["combined_targets"]:
            targets[(index, target["kind"], target["semantic_id"])] = target
    identifiers = {key: f"t{index}" for index, key in enumerate(sorted(targets))}
    # Distinct graphs get separate nodes. A moved target can have different
    # labels, endpoints or membership in the two scopes without cross-view leaks.
    semantics = {
        key: "comparison.target."
        + hashlib.sha256(
            json.dumps(
                [views[key[0]]["key"], views[key[0]]["level"], *key[1:]]
            ).encode()
        ).hexdigest()
        for key in targets
    }
    # Structurizr requires globally unique custom names and edge descriptions.
    # Give the source a separate short final label line; strip that discriminator
    # from the validated SVG before delivery, retaining the original wrapped text.
    markers = {}
    for key, identifier in identifiers.items():
        marker = "[c4:" + identifier + "]"
        while any(
            marker in str(targets[key].get(field, ""))
            for field in ("label", "type", "description")
        ):
            marker = "[" + marker + "]"
        markers[key] = marker
    contract = {
        "version": 1,
        "workspace": {"source": "workspace.dsl", "owner": owner},
        "fragments": [
            {"path": "model.dsl", "owner": owner},
            {"path": "views.dsl", "owner": owner},
        ],
        "elements": [],
        "relationships": [],
        "views": [],
        "renames": [],
    }
    model = []
    for key in sorted(targets, key=lambda key: (key[1] != "element", key)):
        target, identifier = targets[key], identifiers[key]
        display_name = (target.get("label") or key[2]) + "\n" + markers[key]
        if key[1] == "element":
            header = f"{identifier} = element {_quote(display_name)} {_quote(target.get('type') or 'Architecture element')} {_quote(target.get('description'))}"
            contract["elements"].append(
                {
                    "dsl_identifier": identifier,
                    "semantic_id": semantics[key],
                    "fragment": "model.dsl",
                }
            )
        else:
            source = identifiers.get((key[0], "element", target.get("source")))
            destination = identifiers.get(
                (key[0], "element", target.get("destination"))
            )
            if not source or not destination:
                raise ValueError(
                    "Combined relationship has an unavailable endpoint in its view"
                )
            header = f"{identifier} = {source} -> {destination} {_quote(display_name)}"
            contract["relationships"].append(
                {
                    "dsl_identifier": identifier,
                    "semantic_id": semantics[key],
                    "source": source,
                    "destination": destination,
                    "fragment": "model.dsl",
                }
            )
        model.extend(
            [
                header + " {",
                "    properties {",
                f'        "cascade.semanticId" {_quote(semantics[key])}',
                "    }",
                "}",
            ]
        )
    view_lines = []
    for index, view in enumerate(views):
        if layout_views[index] != index:
            shared = views[layout_views[index]]
            for field in (
                "combined_render_key",
                "combined_bindings",
                "combined_label_markers",
            ):
                view[field] = shared[field]
            continue
        key = f"comparison-{index}"
        view["combined_render_key"] = key
        view["combined_bindings"] = {
            semantics[identity]: target["semantic_id"]
            for identity, target in targets.items()
            if identity[0] == index
        }
        view["combined_label_markers"] = {
            semantics[identity]: markers[identity]
            for identity in targets
            if identity[0] == index
        }
        members = {
            identifier
            for identity, identifier in identifiers.items()
            if identity[0] == index
        }
        view_lines.extend(
            [f'custom "{key}" {{', f"    title {_quote('Architecture changes')}"]
        )
        if members:
            view_lines.append("    include " + " ".join(sorted(members)))
        view_lines.extend(["    autoLayout lr", "}"])
        contract["views"].append({"key": key, "fragment": "views.dsl"})
    texts = {
        "workspace.dsl": 'workspace "Architecture comparison" {\n    !impliedRelationships false\n    model {\n        !include model.dsl\n    }\n    views {\n        !include views.dsl\n    }\n}\n',
        "model.dsl": "\n".join(model) + "\n",
        "views.dsl": "\n".join(view_lines) + "\n",
        "workspace.contract.json": json.dumps(contract, sort_keys=True),
    }
    if sum(len(text.encode()) for text in texts.values()) > 2 * 1024 * 1024:
        raise ValueError("Combined diagram source exceeds 2 MiB")
    for name, text in texts.items():
        (directory / name).write_text(text, encoding="utf-8")
    validated = validate_c4_workspace(directory)
    revision = hashlib.sha256(evidence.encode()).hexdigest()
    files = tuple(
        C4SourceFile(
            Path(name),
            Path(name),
            owner,
            revision,
            hashlib.sha256(text.encode()).hexdigest(),
        )
        for name, text in sorted(texts.items())
    )
    closure = C4SourceClosure(
        repository_key,
        repository_key,
        "target",
        Path("."),
        Path("."),
        revision,
        Path("architecture/comparison"),
        Path("workspace.dsl"),
        files,
        "",
        directory,
        validated,
    )
    return replace(closure, digest=closure.computed_digest())


def attach_comparison(
    payload: dict, scheduler, *, renames: dict[str, str] | None = None
) -> None:
    """Admit/reuse one derived render; polling never changes the pinned inputs."""
    views = payload["views"]
    if not views:
        return
    for view in views:
        view.pop("combined", None)
        view.pop("combined_empty", None)
        view["combined_targets"] = comparison_targets(view, renames)
    views = [view for view in views if view["combined_targets"]]
    for view in payload["views"]:
        if not view["combined_targets"]:
            view["combined_empty"] = True
    if not views:
        return
    evidence = json.dumps(payload["snapshot_ids"], sort_keys=True)
    repository_key = next(
        view[side]["repository_key"]
        for view in views
        for side in ("current", "proposed")
        if view.get(side)
    )
    with tempfile.TemporaryDirectory(prefix="cascade-comparison-") as directory:
        closure = comparison_source(
            views,
            Path(directory),
            owner=payload["owner_work_id"],
            evidence=evidence,
            repository_key=repository_key,
        )
        operation = scheduler.admit(
            closure,
            owner=payload["owner_work_id"],
            snapshot_id="comparison:" + evidence,
        )
    scheduled = operation.snapshot()
    payload["comparison_render_operation_id"] = operation.operation_id
    payload["comparison_render_state"] = scheduled.status
    if scheduled.status != "ready":
        payload["state"] = (
            "pending" if scheduled.status in {"pending", "running"} else "render_failed"
        )
        payload["summary"] = (
            "Laying out the combined architecture changes…"
            if payload["state"] == "pending"
            else "Combined diagram unavailable: "
            + (scheduled.failure.message if scheduled.failure else scheduled.status)
        )
        return
    # This read revalidates the durable artifact and its bindings before serving it.
    artifact = scheduler.get_semantic_artifact(
        operation.operation_id, artifact_ref="comparison:" + evidence
    ).render
    manifest = json.loads(artifact.binding_manifest.read_text())
    rows = {row["view_key"]: row for row in manifest["views"]}
    total_bytes = 0
    payload["state"] = "ready"
    for view in views:
        row = rows[view["combined_render_key"]]
        tree = ET.fromstring(_semantic_svg(artifact.binding_manifest.parent, row))
        for node in tree.iter():
            identity = node.get("data-cascade-semantic-id")
            if identity is not None:
                marker = view["combined_label_markers"][identity]
                for label in node.iter():
                    if label.text and marker in label.text:
                        label.text = label.text.replace(marker, "")
                node.set(
                    "data-cascade-semantic-id", view["combined_bindings"][identity]
                )
        svg = ET.tostring(tree, encoding="unicode")
        size = len(svg.encode())
        total_bytes += size
        if size > 4 * 1024 * 1024 or total_bytes > 16 * 1024 * 1024:
            raise ValueError("Combined diagram SVG exceeds the response size limit")
        view["combined"] = {
            "repository_key": repository_key,
            "revision": closure.digest,
            "svg": svg,
            "targets": view["combined_targets"],
        }
