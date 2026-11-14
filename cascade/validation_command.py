"""Repository-owned argv for supervised validation; never interpreted by a shell."""

from pathlib import Path
import tomllib

_DEFAULT_COMMAND = ("python3", "-m", "pytest", "-q")
_REVIEW_SAFETY_TESTS = (
    "tests/test_review_rebase.py",
    "tests/test_review_publication_safeguards.py",
)


def validation_command(root: Path) -> tuple[str, ...]:
    path = Path(root) / "cascade.toml"
    config = tomllib.loads(path.read_text()) if path.is_file() else {}
    command = config.get("validation", {}).get(
        "command", list(_DEFAULT_COMMAND)
    )
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(x, str) and x.strip() for x in command)
    ):
        raise ValueError("validation.command must be a nonempty argv array")
    return tuple(command)


def review_validation_command(
    root: Path,
    worktree: Path,
    changed_paths: tuple[str, ...],
    *,
    configured_command: tuple[str, ...] | None = None,
) -> tuple[str, ...]:
    """Select affected tests for review publication without changing task checks."""

    configured = configured_command or validation_command(root)
    path = Path(root) / "cascade.toml"
    config = tomllib.loads(path.read_text()) if path.is_file() else {}
    if "command" in config.get("validation", {}) or configured != _DEFAULT_COMMAND:
        return configured

    tests_root = (worktree / "tests").resolve()
    selected: set[str] = set()

    def add_test(candidate: str) -> None:
        test = worktree / candidate
        if (
            test.is_file()
            and not test.is_symlink()
            and test.resolve().is_relative_to(tests_root)
        ):
            selected.add(candidate)

    for candidate in _REVIEW_SAFETY_TESTS:
        add_test(candidate)
    for changed in changed_paths:
        parts = Path(changed).parts
        if not parts or ".." in parts or not changed.endswith(".py"):
            continue
        if parts[0] == "tests":
            add_test(changed)
        elif parts[0] == "cascade" and len(parts) >= 2:
            stem = Path(changed).stem
            add_test(f"tests/test_{stem}.py")
            if len(parts) >= 3:
                add_test(f"tests/{parts[1]}/test_{stem}.py")
    return (*configured, *sorted(selected)) if selected else configured
