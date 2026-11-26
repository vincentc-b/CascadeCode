---
id: task_018_002_008
title: Gate the fake provider behind CASCADE_ENABLE_FAKE_PROVIDER=1
tier: task
status: completed
parent: feat_018_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 9b71e805d612c1c5077b46de79c8681840ed5548
created: '2026-10-23'
updated: '2026-10-23'
---
# Gate the fake provider behind CASCADE_ENABLE_FAKE_PROVIDER=1

## Parent Feature

[feat_018_002](../../features/2_active/feat_018_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Why

Task 004 merged (`634df7b`) with the fake provider registered as a real provider: `"fake"` is in `ProviderId` and `ALL_PROVIDER_IDS` in `cascade/agent/providers.py`, `probe_provider("fake")` always reports installed and authenticated, and `resolve_credential("fake")` in `cascade/agent/credentials.py` always returns a credential. So `fake` shows in the War Room provider panel and a real workspace can set `[providers] default = "fake"` and silently run canned turns. Feature spec Test seams / dec_018 / dec_021 require it to be test-only and env-gated.

## Acceptance criteria

- One helper, e.g. `fake_provider_enabled() -> bool` in `cascade/agent/providers.py`, true only when `os.environ.get("CASCADE_ENABLE_FAKE_PROVIDER") == "1"`.
- `ALL_PROVIDER_IDS` is back to `("cursor", "claude", "codex")`; `probe_providers()` never lists `fake`.
- `parse_provider_id("fake")` returns `"fake"` only when enabled; otherwise it raises the existing `unknown provider id: 'fake'` `ProviderConfigError`. Other ids behave exactly as before.
- `probe_provider("fake")` raises the existing unknown-id error when not enabled.
- `resolve_credential("fake")` returns the dummy credential only when enabled; otherwise it returns `None` / behaves like an unknown provider.
- `adapter._dispatch_role` and `planning_turn` `fake` branches stay as they are (unreachable unless parsing accepted `fake`).
- `tests/harness/cascade_up_subprocess.py` sets `env["CASCADE_ENABLE_FAKE_PROVIDER"] = "1"` on the subprocess, next to the existing `CASCADE_DRAIN_INTEGRATION` line.
- `tests/agent/test_providers.py` is restored exactly to its content at `b667be3` (`git checkout b667be3 -- tests/agent/test_providers.py`): three providers, no `fake` unit test, no `fake` in the `parse_provider_id` parametrisation.

## Files likely touched

`cascade/agent/providers.py`, `cascade/agent/credentials.py`, `tests/harness/cascade_up_subprocess.py`, `tests/agent/test_providers.py` (revert only).

## Test plan

No new tests (dec_018). Run `tests/agent/test_providers.py` and the drain integration test `test_feat_018_002_drain_integration.py`; both must pass. If the integration test stops finding the fake provider, the harness env var is missing or config parsing reads providers before the env is set; fix the harness, do not widen the gate.

## Out of scope

Any change to the fake provider's behaviour, the integration tests, or the drain code. Any other provider.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
