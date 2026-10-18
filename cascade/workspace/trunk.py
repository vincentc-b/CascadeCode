"""Product trunk branch resolution (feat_014)."""

from __future__ import annotations

from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.gitutil import _run, has_git
from cascade.workspace.errors import WorkspaceError

_INTEGRATION_PREFIXES = ("epic/", "feat/", "task/")


def is_integration_branch(name: str) -> bool:
    """True for stacked integration lines (not the product trunk)."""

    return any(name.startswith(prefix) for prefix in _INTEGRATION_PREFIXES)


def _list_local_branches(repo: Path) -> list[str]:
    result = _run(["for-each-ref", "--format=%(refname:short)", "refs/heads/"], repo, check=False)
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _has_ref(repo: Path, ref: str) -> bool:
    result = _run(["show-ref", "--verify", "--quiet", ref], repo, check=False)
    return result.returncode == 0


def _is_ancestor(repo: Path, ancestor: str, descendant: str) -> bool:
    result = _run(
        ["merge-base", "--is-ancestor", ancestor, descendant],
        repo,
        check=False,
    )
    return result.returncode == 0


def _unique_trunk_among(repo: Path, branches: list[str]) -> str | None:
    if not branches:
        return None
    roots: list[str] = []
    for candidate in branches:
        if all(
            candidate == other or _is_ancestor(repo, candidate, other) for other in branches
        ):
            roots.append(candidate)
    if len(roots) == 1:
        return roots[0]
    return None


def resolve_product_trunk(root: Path | None = None) -> str:
    """Name the product trunk: ``main`` when present, else the unique non-integration root."""

    repo = resolve_root(root)
    if not has_git(repo):
        raise WorkspaceError(f"not a git repository: {repo}")

    if _has_ref(repo, "refs/heads/main"):
        return "main"

    candidates = [b for b in _list_local_branches(repo) if not is_integration_branch(b)]
    trunk = _unique_trunk_among(repo, candidates)
    if trunk is None:
        if not candidates:
            raise WorkspaceError(
                "cannot resolve product trunk: no local branch outside epic/*, feat/*, or task/*"
            )
        raise WorkspaceError(
            "cannot resolve product trunk: multiple candidate branches "
            f"({', '.join(sorted(candidates))}); use main or disambiguate"
        )
    return trunk
