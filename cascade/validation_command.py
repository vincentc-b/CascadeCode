"""Repository-owned argv for supervised validation; never interpreted by a shell."""

from pathlib import Path
import tomllib


def validation_command(root: Path) -> tuple[str, ...]:
    path = Path(root) / "cascade.toml"
    config = tomllib.loads(path.read_text()) if path.is_file() else {}
    command = config.get("validation", {}).get(
        "command", ["python3", "-m", "pytest", "-q"]
    )
    if (
        not isinstance(command, list)
        or not command
        or not all(isinstance(x, str) and x.strip() for x in command)
    ):
        raise ValueError("validation.command must be a nonempty argv array")
    return tuple(command)
