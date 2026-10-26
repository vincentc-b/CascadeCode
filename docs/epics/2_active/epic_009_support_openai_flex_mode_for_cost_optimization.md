---
id: epic_009
title: Support openai flex mode for cost optimization
tier: epic
status: active
parent: null
children:
- feat_009_001
- feat_009_002
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-22'
updated: '2026-10-26'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Support OpenAI flex mode for cost optimization

## Intent

Let users trade response latency for lower OpenAI/Codex token cost when creating or editing a brief. When the selected provider can honor flex mode, the brief editor offers the option and enables it by default.

The first release implements flex mode for Codex/OpenAI only. The capability contract is provider-neutral so equivalent modes can be added later without changing the brief workflow, but implementing modes for other providers is out of scope for this epic.

## Success criteria

- For a new brief using a flex-capable Codex/OpenAI provider, the brief editor shows a **Flex mode** checkbox and checks it by default.
- A user can opt out; the saved choice is preserved when the brief is reopened.
- Providers that cannot honor flex mode do not show the checkbox and cannot retain an enabled flex value.
- The saved choice reaches the Codex/OpenAI invocation through the normal provider boundary and changes its service mode accordingly.
- Existing briefs and all non-supporting providers continue to behave as they do today.
- The behavior is covered at the provider boundary and at the brief workflow level; redundant low-level coverage is not required.

## Macro-architecture

1. Extend provider metadata with a boolean flex-mode capability. Capability ownership remains with each provider adapter; the UI must not identify support by provider-name checks.
2. Add an optional, backward-compatible flex-mode value to the brief/provider configuration. Absence on an existing brief preserves legacy behavior rather than silently changing an already-created brief.
3. Normalize the configuration at the application/provider boundary: an unsupported provider cannot execute or persist flex mode as enabled.
4. Map the normalized value in the Codex/OpenAI adapter to the integration's supported flex execution option.
5. Bind the brief editor checkbox to the same persisted field. Visibility comes from provider capability; new capable selections default on, while an explicit user opt-out remains off.

## Cross-module constraints

- Use the existing provider configuration and invocation path; do not add an OpenAI-only side channel.
- Provider capability metadata is the single source of truth for UI visibility and server-side validation.
- The stored field must be optional so older serialized briefs remain readable.
- Unsupported or unavailable flex mode must degrade to normal execution without breaking brief creation. Do not silently send a provider option that the adapter cannot honor.
- Log/telemetry may identify that flex mode was selected or normalized, but must not expose prompts, credentials, or provider secrets.
- Copy should explain the tradeoff plainly: lower cost with potentially higher latency. Do not promise an exact discount in product copy unless the provider supplies a stable, authoritative value.
- Scope excludes generalized pricing comparison, latency estimates, automatic mode selection, and equivalent implementations for other providers.

## Core dependencies

- Existing provider capability/configuration model.
- Existing brief create/edit persistence and validation path.
- Existing Codex/OpenAI command or request construction.
- No new external service dependency is expected.

## Feature breakdown

1. **feat_009_001 — Model provider flex capability and execution plumbing**
   - Define provider-neutral capability and optional brief setting.
   - Enforce normalization for unsupported providers and backward compatibility for legacy briefs.
   - Map enabled/disabled flex mode into Codex/OpenAI execution.
   - Add focused provider-boundary integration coverage.

2. **feat_009_002 — Brief editor flex-mode control** (depends on feat_009_001)
   - Render the checkbox from provider capability metadata.
   - Default it on for a new capable-provider brief.
   - Preserve explicit opt-out and normalize provider switching.
   - Add focused brief-workflow coverage.

## Delivery sequence

Ship feat_009_001 before feat_009_002. The first feature establishes the persisted contract and makes direct or non-UI brief creation safe; the second exposes it in the product workflow. The epic is complete when both features meet their acceptance criteria and the end-to-end brief-to-provider path is verified.

## Open questions

- None blocking. During feat_009_001 implementation, confirm the exact Codex/OpenAI invocation mechanism supported by the pinned integration version. If that version cannot honor flex mode, do not advertise the capability; treat the issue as a dependency update decision rather than emulating flex behavior.

## Decision log

- 2026-10-22 · Human · Brief approved through merge request review.
- 2026-10-26 · Epic Manager · Limit the first release to Codex/OpenAI while defining a provider-neutral capability contract.
- 2026-10-26 · Epic Manager · Default flex mode on only for newly created briefs with a capable provider; preserve legacy behavior for existing briefs with no stored value.
- 2026-10-26 · Epic Manager · Split delivery into provider/execution plumbing followed by the dependent brief-editor control.

- `dec_001` · 2026-10-26 · Epic Manager · **Scope**
  Chose Ship Codex/OpenAI flex mode first behind a provider-neutral capability contract..
  Rationale: This satisfies the approved user outcome without committing the epic to unspecified implementations for other providers.
  Honors: Intent and success criteria; extensibility requirement..
## Amendment log

_(none)_
