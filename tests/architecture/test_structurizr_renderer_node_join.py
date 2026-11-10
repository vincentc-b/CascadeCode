from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET

from cascade.workspace import verify_and_sanitize_hit_targets


IMAGE = (
    "structurizr/structurizr@"
    "sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c"
)
FIXTURES = Path(__file__).parent / "fixtures" / "renderer_node_join"
VIEW_KEY = "renderer-node-join"
EXPECTED_BASELINE = {
    "container.worker.first",
    "container.worker.second",
    "deployment.cloud.first",
    "deployment.cloud.second",
    "deployment.region.first",
    "deployment.region.second",
    "relationship.first.second.reads",
    "relationship.first.second.writes",
}
EXPECTED_REMOVED = {
    "container.worker.first",
    "deployment.cloud.first",
    "deployment.region.first",
}


def _run(args: list[str], *, timeout: int = 70) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _container_args(root: Path) -> list[str]:
    return [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=256",
        "--memory=1536m",
        "--cpus=2",
        "--tmpfs",
        "/tmp:rw,size=512m",
        "--user",
        f"{os.getuid()}:{os.getgid()}",
        "-e",
        "HOME=/tmp",
        "-e",
        "PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
        "-e",
        "PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1",
        "-v",
        f"{root}:/usr/local/structurizr:rw",
        IMAGE,
    ]


def _workspace_from_static_export(static_dir: Path) -> dict:
    source = (static_dir / "workspace.js").read_text()
    match = re.fullmatch(r"const jsonAsString = '([A-Za-z0-9+/=]+)';", source)
    assert match, "unexpected Structurizr static workspace wrapper"
    return json.loads(base64.b64decode(match.group(1)))


def _objects_by_export_id(workspace: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}

    def walk(value: object) -> None:
        if isinstance(value, dict):
            identifier = value.get("id")
            if isinstance(identifier, str):
                previous = result.setdefault(identifier, value)
                assert previous is value or previous == value
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(workspace["model"])
    return result


def _semantic_id(model_id: str, objects: dict[str, dict]) -> str:
    seen: set[str] = set()
    current_id = model_id
    while current_id not in seen:
        seen.add(current_id)
        current = objects[current_id]
        semantic_id = current.get("properties", {}).get("cascade.id")
        if semantic_id:
            return semantic_id
        if "linkedRelationshipId" in current:
            current_id = current["linkedRelationshipId"]
            continue
        if "containerId" in current:
            current_id = current["containerId"]
            continue
        break
    raise AssertionError(f"model ID {model_id} has no unambiguous cascade.id chain")


def _run_probe(root: Path) -> None:
    script = """
set -eu
mkdir -p /tmp/lib /tmp/classes
unzip -q /usr/local/structurizr.war \
  'WEB-INF/lib/gson-*.jar' \
  'WEB-INF/lib/playwright-*.jar' \
  'WEB-INF/lib/driver-*.jar' \
  -d /tmp/lib
javac -cp '/tmp/lib/WEB-INF/lib/*' -d /tmp/classes RendererBindingProbe.java
java -cp '/tmp/classes:/tmp/lib/WEB-INF/lib/*' RendererBindingProbe \
  static bindings.json bound.svg renderer-node-join
"""
    args = _container_args(root)
    args[len(args) - 1 : len(args) - 1] = ["--entrypoint", "/bin/sh"]
    _run([*args, "-c", script], timeout=70)


def _render(tmp_path: Path, fixture_name: str, *, stock_svg: bool = False) -> dict:
    root = tmp_path / fixture_name
    root.mkdir(mode=0o755)
    shutil.copy(FIXTURES / f"{fixture_name}.dsl", root / "workspace.dsl")
    shutil.copy(FIXTURES / "RendererBindingProbe.java", root)
    (root / "static").mkdir(mode=0o755)
    (root / "stock").mkdir(mode=0o755)

    base = _container_args(root)
    _run([*base, "validate", "-workspace", "workspace.dsl"])
    _run(
        [
            *base,
            "export",
            "-workspace",
            "workspace.dsl",
            "-format",
            "static",
            "-output",
            "static",
        ]
    )
    if stock_svg:
        _run(
            [
                *base,
                "export",
                "-workspace",
                "workspace.dsl",
                "-format",
                "svg",
                "-output",
                "stock",
            ]
        )
    _run_probe(root)

    workspace = _workspace_from_static_export(root / "static")
    objects = _objects_by_export_id(workspace)
    expected = EXPECTED_REMOVED if fixture_name == "removed" else EXPECTED_BASELINE
    verified = verify_and_sanitize_hit_targets(
        workspace=workspace,
        view_key=VIEW_KEY,
        raw_bindings=root / "bindings.json",
        raw_svg=root / "bound.svg",
        sanitized_svg=root / "sanitized-bound.svg",
        expected_semantic_ids=frozenset(expected),
    )
    bindings = json.loads((root / "bindings.json").read_text())
    semantic_by_renderer = {
        binding.renderer_node_id: binding.semantic_id for binding in verified
    }

    svg = ET.parse(root / "sanitized-bound.svg")
    svg_bindings = {
        node.attrib["id"]: (
            node.attrib["data-cascade-model-kind"],
            node.attrib["data-cascade-export-id"],
        )
        for node in svg.iter()
        if "data-cascade-export-id" in node.attrib
    }
    assert svg_bindings == {
        binding["rendererNodeId"]: (binding["kind"], binding["modelId"])
        for binding in bindings
    }
    return {
        "root": root,
        "workspace": workspace,
        "objects": objects,
        "bindings": bindings,
        "semantic_by_renderer": semantic_by_renderer,
    }


def test_renderer_nodes_join_to_same_export_semantic_ids(tmp_path: Path) -> None:
    inspected = json.loads(_run(["docker", "image", "inspect", IMAGE]).stdout)[0]
    assert IMAGE in inspected["RepoDigests"]
    assert (inspected["Os"], inspected["Architecture"]) == ("linux", "amd64")

    baseline = _render(tmp_path, "baseline", stock_svg=True)
    reordered = _render(tmp_path, "reordered")
    removed = _render(tmp_path, "removed")

    baseline_semantics = set(baseline["semantic_by_renderer"].values())
    reordered_semantics = set(reordered["semantic_by_renderer"].values())
    removed_semantics = set(removed["semantic_by_renderer"].values())
    assert baseline_semantics == reordered_semantics == EXPECTED_BASELINE
    assert removed_semantics == EXPECTED_REMOVED
    assert baseline_semantics - removed_semantics == EXPECTED_BASELINE - EXPECTED_REMOVED

    # Reordering changes artifact-local exporter IDs, but not the semantic result.
    def model_ids_by_semantic(render: dict) -> dict[str, str]:
        return {
            _semantic_id(binding["modelId"], render["objects"]): binding["modelId"]
            for binding in render["bindings"]
        }

    baseline_ids = model_ids_by_semantic(baseline)
    reordered_ids = model_ids_by_semantic(reordered)
    assert any(
        baseline_ids[semantic_id] != reordered_ids[semantic_id]
        for semantic_id in EXPECTED_BASELINE
    )

    # Duplicate rendered labels and parallel endpoints are deliberately present.
    baseline_objects = baseline["objects"]
    mapped_ids = {binding["modelId"] for binding in baseline["bindings"]}
    assert sum(
        baseline_objects[model_id].get("name") == "Region" for model_id in mapped_ids
    ) == 2
    instances = [
        baseline_objects[model_id]
        for model_id in mapped_ids
        if "containerId" in baseline_objects[model_id]
    ]
    assert len(instances) == 2
    assert {
        baseline_objects[instance["containerId"]]["name"] for instance in instances
    } == {"Worker"}
    relationships = [
        baseline_objects[binding["modelId"]]
        for binding in baseline["bindings"]
        if binding["kind"] == "relationship"
    ]
    assert len(relationships) == 2
    assert len({(item["sourceId"], item["destinationId"]) for item in relationships}) == 1

    # Stock SVG alone is intentionally insufficient: the pinned exporter strips
    # model-id, data-type, and classes before writing the file.
    stock_svg = (baseline["root"] / "stock" / f"{VIEW_KEY}.svg").read_text()
    assert "model-id=" not in stock_svg
    assert "data-cascade-export-id=" not in stock_svg
    assert all(semantic_id not in stock_svg for semantic_id in EXPECTED_BASELINE)
