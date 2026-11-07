"""War Room integration coverage for human dependency actions."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.epic.dependency_bootstrap import (
    BootstrapEntryScope,
    BootstrapLimits,
    BootstrapScope,
    FeasibilityArtifact,
    create_bootstrap,
    read_bootstrap,
)
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestDraft,
    EnvironmentIdentity,
    InstallationBinding,
    write_dependency_manifest,
)
from cascade.epic.dependency_runner import (
    OperationFailure,
    OperationObservation,
    OperationRequest,
)
from cascade.war_room.server import serve
from cascade.war_room.human_auth import LocalHumanIdentityVerifier
from cascade.war_room.dependency_routes import INSTALLATION_APPROVAL_PATH
from tests.support import add_doc, make_repo


class Executor:
    def __init__(self, observations: list[OperationObservation]) -> None:
        self.observations = observations
        self.requests: list[OperationRequest] = []

    def execute(self, request: OperationRequest) -> OperationObservation:
        self.requests.append(request)
        return self.observations.pop(0)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def _server(
    root: Path,
    *,
    human: AuthenticatedHuman | None = None,
    executor: Executor | None = None,
) -> Iterator[str]:
    server = serve(
        root=root,
        host="127.0.0.1",
        port=_free_port(),
        human_identity_verifier=(
            LocalHumanIdentityVerifier(human.subject, "test-human-token")
            if human is not None
            else None
        ),
        dependency_executor=executor,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _post(
    base: str,
    path: str,
    body: dict,
    *,
    authenticated: bool = False,
    cookie: str | None = None,
) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers["Authorization"] = "Bearer test-human-token"
    if cookie is not None:
        headers["Cookie"] = cookie
    request = urllib.request.Request(
        base + path,
        method="POST",
        data=json.dumps(body).encode(),
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def _establish_local_session(base: str) -> str:
    request = urllib.request.Request(
        base + "/api/local_human_session",
        method="POST",
        data=json.dumps({"token": "test-human-token"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        assert response.status == 200
        return response.headers["Set-Cookie"].split(";", 1)[0]


def _target() -> EnvironmentIdentity:
    return EnvironmentIdentity(
        "api-ci",
        "container",
        "linux",
        "x86_64",
        runner="api-runner",
        repository="example/cascade",
        worktree="/work/cascade",
        sandbox="container",
        runtime="python-3.12",
        container_digest="sha256:api-runner",
    )


def _prepare(root: Path) -> tuple[DependencyEntry, BootstrapScope]:
    target = _target()
    entry = DependencyEntry(
        dependency_id="dep_tool",
        version="1.2.3",
        source="https://tool.example/1.2.3/tool.tgz",
        digest="sha256:tool",
        target_environment=target,
        install_scope="project-local",
        install_destination=".tools/tool",
        operation="install tool 1.2.3 into .tools/tool",
        cleanup_plan="remove .tools/tool",
        verification_recipe=".tools/tool --version",
        expected_verification_result="tool 1.2.3",
        feasibility_proof_requirements=("adapter_probe",),
        feasibility_proof_references=("adapter_probe",),
        lock_references=("adapter_probe",),
    )
    manifest = write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(target, None, False, (entry,)),
        root=root,
        expected_revision=0,
    )
    scope = BootstrapScope(
        manifest.revision,
        (
            BootstrapEntryScope(
                entry.dependency_id,
                entry.source,
                entry.integrity_reference or entry.digest,
                entry.operation,
                entry.verification_recipe,
                (entry.install_destination or ".tools/tool",),
                entry.install_destination or ".tools/tool",
                entry.cleanup_plan,
            ),
        ),
        (
            FeasibilityArtifact(
                "adapter_probe",
                "python bootstrap/probe.py",
                target,
                ("bootstrap/probe.py",),
                (".cascade/bootstrap/result.json",),
                "remove probe output",
            ),
        ),
        BootstrapLimits(10, 3, 4096),
    )
    create_bootstrap("epic_001", scope, root=root)
    return entry, scope


def _observation(
    *, failure: OperationFailure | None = None, output: str = "tool 1.2.3"
) -> OperationObservation:
    return OperationObservation(
        _target(),
        1 if failure else 0,
        output,
        "1.2.3",
        "sha256:tool",
        failure,
    )


def test_dependency_actions_require_a_trusted_human_boundary(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    entry, _scope = _prepare(root)

    # A server-wide identity is intentionally not a request principal.
    server = serve(
        root=root,
        host="127.0.0.1",
        port=_free_port(),
        authenticated_human=AuthenticatedHuman("injected@example.test"),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{server.server_port}"
        status, payload = _post(
            base,
            "/api/approve_dependency_installations",
            {
                "epic_id": "epic_001",
                "manifest_revision": 1,
                "entries": [
                    {
                        "dependency_id": entry.dependency_id,
                        "binding": InstallationBinding.from_entry(entry).to_dict(),
                    }
                ],
            },
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == 401
    assert payload["refusal"]["code"] == "human_authentication_required"
    assert payload["dependency_status"]["epic_id"] == "epic_001"

    approval_body = {
        "epic_id": "epic_001",
        "manifest_revision": 1,
        "entries": [
            {
                "dependency_id": entry.dependency_id,
                "binding": InstallationBinding.from_entry(entry).to_dict(),
            }
        ],
    }
    with _server(root, human=AuthenticatedHuman("verified@example.test")) as base:
        authenticated_status, _ = _post(
            base, INSTALLATION_APPROVAL_PATH, approval_body, authenticated=True
        )
        later_status, later = _post(base, INSTALLATION_APPROVAL_PATH, approval_body)

    assert authenticated_status == 200
    assert later_status == 401
    assert later["refusal"]["code"] == "human_authentication_required"


def test_review_approve_and_duplicate_ping_remain_distinct(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    entry, scope = _prepare(root)
    executor = Executor(
        [
            _observation(failure=OperationFailure.COMMAND_FAILED),
            _observation(),
            _observation(),
            _observation(output="adapter succeeded"),
        ]
    )
    kickoffs = []
    monkeypatch.setattr(
        "cascade.epic.dependency_resume._kickoff_planning", kickoffs.append
    )
    human = AuthenticatedHuman("operator@example.test")

    with _server(root, human=human, executor=executor) as base:
        cookie = _establish_local_session(base)
        bootstrap = read_bootstrap("epic_001", root=root)
        assert bootstrap is not None
        review_status, reviewed = _post(
            base,
            "/api/review_dependency_bootstrap",
            {
                "epic_id": "epic_001",
                "bootstrap_revision": bootstrap.revision,
                "scope_fingerprint": scope.fingerprint,
                "scope": scope.to_dict(),
            },
            cookie=cookie,
        )
        assert review_status == 200
        assert reviewed["dependency_status"]["dependencies"][0][
            "installation_approval"
        ]["state"] == "missing"

        binding = InstallationBinding.from_entry(entry).to_dict()
        approval_status, approved = _post(
            base,
            "/api/approve_dependency_installations",
            {
                "epic_id": "epic_001",
                "manifest_revision": 1,
                "entries": [
                    {"dependency_id": entry.dependency_id, "binding": binding}
                ],
            },
            cookie=cookie,
        )
        assert approval_status == 200
        approval = approved["approvals"][0]
        assert approval["approver_id"] == human.subject

        ping_body = {
            "epic_id": "epic_001",
            "request_id": "ping-api-1",
            "approval_references": {
                entry.dependency_id: approval["approval_id"]
            },
        }
        ping_status, pinged = _post(
            base, "/api/ping_dependency_team", ping_body, cookie=cookie
        )
        duplicate_status, duplicate = _post(
            base, "/api/ping_dependency_team", ping_body, cookie=cookie
        )

    assert ping_status == duplicate_status == 200
    assert pinged["ping"]["ready"] is True
    assert duplicate["ping"]["deduplicated"] is True
    assert len(executor.requests) == 4
    assert len(kickoffs) == 1
