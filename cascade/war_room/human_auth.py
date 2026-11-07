"""Request-scoped local-human authentication for authority-granting actions."""

from __future__ import annotations

import getpass
import hmac
import os
import secrets
from dataclasses import dataclass
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Mapping, Protocol

from cascade.epic.dependency_approvals import AuthenticatedHuman

SESSION_COOKIE = "cascade_human_session"
_TOKEN_PATH = Path(".cascade") / "war-room-human-token"


class HumanIdentityVerifier(Protocol):
    """Trusted boundary invoked independently for every HTTP request."""

    def verify_request(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        client_address: tuple[str, int],
    ) -> AuthenticatedHuman | None: ...


@dataclass(frozen=True, slots=True)
class LocalHumanIdentityVerifier:
    """Authenticate possession of the operator's protected launch capability."""

    subject: str
    token: str

    def verify_request(
        self,
        *,
        method: str,
        path: str,
        headers: Mapping[str, str],
        client_address: tuple[str, int],
    ) -> AuthenticatedHuman | None:
        del method, path
        if client_address[0] not in {"127.0.0.1", "::1"}:
            return None
        supplied = _cookie_value(headers.get("Cookie", ""))
        authorization = headers.get("Authorization", "")
        if authorization.startswith("Bearer "):
            supplied = authorization.removeprefix("Bearer ").strip()
        if not supplied or not hmac.compare_digest(supplied, self.token):
            return None
        return AuthenticatedHuman(self.subject)

    def accepts_token(self, token: object) -> bool:
        return isinstance(token, str) and hmac.compare_digest(token, self.token)


def load_or_create_local_human_verifier(root: Path) -> LocalHumanIdentityVerifier:
    """Return a restart-stable verifier whose secret is readable only by its owner."""

    path = Path(root).resolve() / _TOKEN_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        token = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        token = secrets.token_urlsafe(32)
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        try:
            descriptor = os.open(path, flags, 0o600)
        except FileExistsError:
            token = path.read_text(encoding="utf-8").strip()
        else:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(token + "\n")
    if not token:
        raise RuntimeError(f"local human authentication token is empty: {path}")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return LocalHumanIdentityVerifier(f"local:{getpass.getuser()}", token)


def _cookie_value(raw: str) -> str | None:
    cookie = SimpleCookie()
    try:
        cookie.load(raw)
    except Exception:
        return None
    morsel = cookie.get(SESSION_COOKIE)
    return morsel.value if morsel is not None else None
