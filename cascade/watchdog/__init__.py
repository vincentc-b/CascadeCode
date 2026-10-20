"""Watchdog, append-only queues, and dispatch law."""

from cascade.watchdog.config import (
    AutomationConfig,
    ConfigError,
    ModelsTable,
    ProvidersConfig,
    read_automation_config,
    read_models_table,
    read_providers_config,
    task_parallelism,
)
from cascade.watchdog.model_resolve import (
    ModelConfigError,
    ModelSource,
    ProviderSource,
    ResolvedBackend,
    ResolvedModel,
    resolve_backend,
    resolve_model,
)
from cascade.watchdog.role_skills import (
    RoleSkillDefaults,
    default_role_skill_paths,
    load_role_skills_context,
    resolve_effective_skills,
)
from cascade.watchdog.dispatch import activate_epic, dispatch_feature, dispatch_task
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.hooks import register_boot_hook, register_teardown_hook
from cascade.watchdog.loop import run_watchdog, watchdog_tick
from cascade.watchdog.types import (
    DispatchRequest,
    DispatchResult,
    Event,
    Principal,
)

__all__ = [
    "ConfigError",
    "AutomationConfig",
    "ModelConfigError",
    "ModelSource",
    "ModelsTable",
    "ProviderSource",
    "ProvidersConfig",
    "ResolvedBackend",
    "ResolvedModel",
    "DispatchRequest",
    "DispatchResult",
    "Event",
    "Principal",
    "activate_epic",
    "append_event",
    "dispatch_feature",
    "dispatch_task",
    "read_events",
    "read_automation_config",
    "read_models_table",
    "read_providers_config",
    "resolve_backend",
    "resolve_model",
    "RoleSkillDefaults",
    "default_role_skill_paths",
    "load_role_skills_context",
    "resolve_effective_skills",
    "register_boot_hook",
    "register_teardown_hook",
    "run_watchdog",
    "task_parallelism",
    "watchdog_tick",
]
