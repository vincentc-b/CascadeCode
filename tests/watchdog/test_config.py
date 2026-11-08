"""cascade.toml task_parallelism and [models]."""

from pathlib import Path

import pytest

from cascade.watchdog import (
    ConfigError,
    HealthAuditConfig,
    ModelsTable,
    ProvidersConfig,
    dispatch_task,
    read_models_table,
    completed_epic_display_limit,
    read_automation_config,
    read_health_audit_config,
    read_providers_config,
    task_parallelism,
)
from cascade.watchdog.config import provider_permission_mode
from cascade.board import read_doc
from tests.support import add_doc, make_repo


def test_health_audit_config_defaults_independently_of_automation(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    assert read_automation_config(root).enabled is False
    assert read_health_audit_config(root) == HealthAuditConfig(
        enabled=True, interval_seconds=1800
    )

    (root / "cascade.toml").write_text(
        "[automation]\nenabled = false\n\n"
        "[automation.health_audit]\nenabled = true\ninterval = \"2h\"\n",
        encoding="utf-8",
    )
    assert read_health_audit_config(root) == HealthAuditConfig(
        enabled=True, interval_seconds=7200
    )


@pytest.mark.parametrize(
    ("interval", "seconds"),
    [("60s", 60), ("1m", 60), ("90m", 5400), ("24h", 86400), ("1d", 86400)],
)
def test_health_audit_config_accepts_bounded_integer_durations(
    tmp_path: Path, interval: str, seconds: int
) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text(
        f'[automation.health_audit]\nenabled = false\ninterval = "{interval}"\n',
        encoding="utf-8",
    )
    assert read_health_audit_config(root) == HealthAuditConfig(
        enabled=False, interval_seconds=seconds
    )


@pytest.mark.parametrize(
    "literal",
    [
        '""',
        '"0m"',
        '"-1m"',
        '"1.5h"',
        '"01m"',
        '"59s"',
        '"24h1m"',
        '"25h"',
        '"2d"',
        '"30M"',
        "30",
        "true",
    ],
)
def test_health_audit_config_rejects_invalid_intervals_explicitly(
    tmp_path: Path, literal: str
) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text(
        f"[automation.health_audit]\ninterval = {literal}\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError, match=r"automation\.health_audit\.interval"):
        read_health_audit_config(root)


def test_invalid_health_audit_config_does_not_break_automation_or_legacy_health(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text(
        "[automation]\nenabled = true\npoll_seconds = 9\n\n"
        "[automation.health_audit]\nenabled = \"yes\"\n\n"
        "[supervisor_health]\nsweep_seconds = 12\n",
        encoding="utf-8",
    )

    assert read_automation_config(root).enabled is True
    from cascade.watchdog import supervisor_health_sweep_seconds

    assert supervisor_health_sweep_seconds(root) == 12.0
    with pytest.raises(ConfigError, match=r"health_audit\.enabled must be a boolean"):
        read_health_audit_config(root)


def test_completed_epic_display_limit_defaults_and_fallbacks(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    assert completed_epic_display_limit(root) == 10

    (root / "cascade.toml").write_text(
        "[war_room]\ncompleted_epic_display_limit = 5\n", encoding="utf-8"
    )
    assert completed_epic_display_limit(root) == 5

    (root / "cascade.toml").write_text(
        "[war_room]\ncompleted_epic_display_limit = 0\n", encoding="utf-8"
    )
    assert completed_epic_display_limit(root) == 10


def test_parallelism_defaults_and_rejects_non_integers(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    assert task_parallelism(root) == 4

    (root / "cascade.toml").write_text("# supervisor\n\n", encoding="utf-8")
    assert task_parallelism(root) == 4

    (root / "cascade.toml").write_text(
        "# Workspace supervisor config.\ntask_parallelism = 4\n",
        encoding="utf-8",
    )
    assert task_parallelism(root) == 4

    (root / "cascade.toml").write_text('task_parallelism = "4"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        task_parallelism(root)

    (root / "cascade.toml").write_text("task_parallelism = true\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        task_parallelism(root)

    (root / "cascade.toml").write_text("task_parallelism = -1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        task_parallelism(root)

    (root / "cascade.toml").write_text("task_parallelism = 0\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        task_parallelism(root)

    (root / "cascade.toml").write_text("task_parallelism = 8\n", encoding="utf-8")
    assert task_parallelism(root) == 8

    (root / "cascade.toml").write_text("task_parallelism = [\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        task_parallelism(root)


def test_bad_config_does_not_dispatch(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    (root / "cascade.toml").write_text("task_parallelism = 1.5\n", encoding="utf-8")
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    with pytest.raises(ConfigError):
        dispatch_task("task_001", "human", root=root)
    doc = read_doc("task_001", root=root)
    assert doc.meta.status == "backlog"
    assert doc.meta.path.parent.name == "1_backlog"


def test_models_table_missing_file_and_section(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    assert read_models_table(root) == ModelsTable()

    (root / "cascade.toml").write_text("task_parallelism = 4\n", encoding="utf-8")
    assert read_models_table(root) == ModelsTable()


def test_models_table_valid_tiers_and_roles(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text(
        """
[models]
epic = "epic-default"
feature = "feature-default"
task = "task-default"
boss = "boss-default"

[models.roles]
epic_architect = "architect-override"
swe = "auto"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    table = read_models_table(root)
    assert table == ModelsTable(
        epic="epic-default",
        feature="feature-default",
        task="task-default",
        boss="boss-default",
        roles={"epic_architect": "architect-override", "swe": "auto"},
    )


def test_models_table_rejects_bad_values(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)

    (root / "cascade.toml").write_text("[models]\nepic = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        read_models_table(root)

    (root / "cascade.toml").write_text('[models]\nfeature = "  "\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        read_models_table(root)

    (root / "cascade.toml").write_text(
        "[models]\nroles = 'not-a-table'\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        read_models_table(root)

    (root / "cascade.toml").write_text(
        "[models.roles]\nswe = ''\n", encoding="utf-8"
    )
    with pytest.raises(ConfigError):
        read_models_table(root)


def test_models_table_malformed_toml(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text("[models\nepic = x\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid cascade.toml"):
        read_models_table(root)


def test_providers_and_models_both_present_is_config_error(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text(
        """
[models]
task = "legacy-task"

[providers]
default = "cursor"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="both \\[providers\\] and \\[models\\]"):
        read_providers_config(root)


def test_legacy_models_maps_to_cursor_default(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text(
        """
[models]
epic = "legacy-epic"
task = "legacy-task"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    cfg = read_providers_config(root)
    assert cfg.default == "cursor"
    assert cfg.tables["cursor"] == ModelsTable(epic="legacy-epic", task="legacy-task")
    assert cfg.tables["claude"] == ModelsTable()
    assert cfg.tables["codex"] == ModelsTable()


def test_providers_new_shape_round_trip(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text(
        """
[providers]
default = "claude"

[providers.cursor]
task = "cursor-task"

[providers.claude]
task = "claude-task"
epic = "claude-epic"

[providers.claude.roles]
swe = "claude-role-swe"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    cfg = read_providers_config(root)
    assert cfg == ProvidersConfig(
        default="claude",
        tables={
            "cursor": ModelsTable(task="cursor-task"),
            "claude": ModelsTable(
                task="claude-task",
                epic="claude-epic",
                roles={"swe": "claude-role-swe"},
            ),
            "codex": ModelsTable(),
        },
    )


def test_provider_permission_mode_defaults_and_yolo_opt_in(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text(
        """
[providers]
default = "cursor"

[providers.cursor]
epic = "composer"

[providers.cursor.launch]
permissions = "yolo"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    assert provider_permission_mode(root, "cursor") == "yolo"
    assert provider_permission_mode(root, "codex") == "default"

    (root / "cascade.toml").write_text(
        '[providers]\ndefault = "cursor"\n[providers.cursor.launch]\npermissions = "wide"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="default.*yolo"):
        provider_permission_mode(root, "cursor")
