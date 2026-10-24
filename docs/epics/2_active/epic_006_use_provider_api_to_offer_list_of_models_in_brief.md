---
id: epic_006
title: Use provider api to offer list of models in brief
tier: epic
status: active
parent: null
children:
- feat_006_001
- feat_006_002
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-21'
updated: '2026-10-24'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
plan_approved_at: '2026-10-24T18:13:38.563291+00:00'
---
# Use provider API to offer list of models in brief

## Intent

Brief creation must not accept provider/model combinations that downstream agents cannot use. Replace free-text model entry with choices discovered from installed, authenticated provider APIs, and capture defaults for every role layer created from the brief.

The initial delivery validates this at brief-creation time without introducing a background synchronization service.

### Success criteria

- The provider selector contains only providers that are installed/configured and successfully report availability.
- Offered models come from the selected provider's actual API response; the UI does not own a static model list.
- Brief creation uses selectors, not arbitrary model text, for all configured epic, feature, and task roles.
- For providers and models that support configurable reasoning, brief creation offers supported reasoning levels for each role, including the provider default; unsupported combinations use their default without a selector.
- The selected provider and per-role model defaults are persisted and used by downstream work creation.
- Selected per-role reasoning levels are persisted and used by downstream work creation; leaving a level at default preserves provider behavior.
- One unavailable or failing provider does not prevent healthy providers from being offered.
- When no provider is usable, submission is disabled with a clear, recoverable state.
- A representative end-to-end test covers discovery, selection, persistence, and reload/use of saved defaults.

## Macro-architecture

1. Each provider integration exposes capability discovery returning its canonical provider identifier, current models, and supported reasoning levels or default behavior for each model when available.
2. A provider inventory service queries only installed/configured integrations, isolates adapter failures, normalizes results, and applies a small bounded freshness cache around successful responses.
3. The existing application boundary exposes that inventory to brief creation, including loading, empty-availability, and refresh-failure states.
4. The brief UI selects one available provider and renders model selectors for every epic, feature, and task role represented by the brief schema. For models with configurable reasoning, it also renders a per-role reasoning selector with a default choice. Changing provider or model clears or revalidates incompatible selections.
5. The existing brief write path validates selections against the current inventory, persists provider plus per-role model and reasoning defaults, and supplies those defaults when downstream feature and task work is minted.

Provider-specific API and authentication behavior stays inside existing integrations; the UI consumes one normalized contract.

## Cross-module constraints

- Provider APIs are authoritative for selectable models. Static UI model catalogs are out of scope.
- Credentials and raw provider errors must not cross the application boundary or appear in client-visible responses/logs.
- Discovery is fault-isolated: one timeout, missing login, or absent installation makes only that provider unavailable.
- Cache freshness must be explicit and bounded. Refresh on expiry or user request is sufficient; a scheduler or durable background job is not required.
- The server revalidates submitted provider/model identifiers; client selectors are not a trust boundary.
- The server also validates non-default reasoning levels against the selected provider/model capability; unsupported combinations cannot accept an override.
- Existing saved briefs with unavailable historical values remain readable; this epic governs new or edited selections and does not require migration.
- Reuse the existing brief schema and role naming. Expand it only where full-stack defaults cannot already be represented.
- Concentrate tests on the provider inventory boundary and one end-to-end brief flow; redundant per-component coverage is not required.

## Core dependencies

- Existing provider integration registry/configuration and authentication state.
- Provider APIs that enumerate usable models.
- Existing brief creation/read persistence boundary.
- Existing propagation path from epic defaults to feature/task work.

No new external service, durable cache, or scheduler is a prerequisite.

## Feature breakdown

1. **feat_006_001 — Discover available providers and models**
   - Add normalized discovery across installed/configured provider integrations.
- Expose supported reasoning levels and default behavior where a provider/model offers configurable reasoning.
   - Filter unavailable providers, isolate partial failures, and apply bounded caching/refresh.
   - Expose a safe UI-facing inventory contract.
   - Prove API-derived results, filtering, partial failure, and refresh behavior.

2. **feat_006_002 — Select provider and full-stack model defaults in brief**  
   Depends on: feat_006_001
   - Replace free-text model fields with inventory-backed selectors.
   - Cover all epic, feature, and task roles represented by the brief schema, including per-role reasoning selectors when supported and a default choice.
   - Validate and persist model and reasoning selections, then propagate them through downstream work creation.
   - Cover loading/empty/error states and one representative end-to-end flow.

## Non-goals

- A continuously running or durable provider synchronization subsystem.
- Model pricing, benchmarking, recommendation, ranking, or automatic “best model” selection.
- Installing providers or signing users into providers from the brief screen.
- Migrating or rewriting historical briefs.
- Supporting arbitrary model identifiers that the provider API did not return.

## Open questions

- During feature planning, map the existing brief-schema role keys to the epic/feature/task selectors; preserve current role names.
- Confirm each provider's model-list API and authentication probe. A provider without safe enumeration remains unavailable rather than falling back to a hard-coded list.
- Choose the shortest cache TTL that avoids noisy calls while keeping availability credible; this is an implementation parameter, not a product promise.

## Decision log

- 2026-10-21 · Human · Brief approved through merge request review.
- 2026-10-24 · Epic Manager · Deliver provider discovery as a shared, fault-isolated backend inventory before changing the brief UI.
- 2026-10-24 · Epic Manager · Use bounded on-demand caching; exclude periodic background synchronization from the initial scope.
- 2026-10-24 · Epic Manager · Use one selected provider with per-role model defaults across epic, feature, and task layers; reject arbitrary new model text.
- 2026-10-24 · Epic Manager · Preserve historical briefs without migration; validate new or edited selections against current discovery.
- 2026-10-24 · Human · Include supported reasoning-level overrides in brief selectors; retain provider defaults when no override is chosen.

- `dec_001` · 2026-10-24 · Epic Manager · **Architecture sequencing**
  Chose Establish a shared, fault-isolated provider/model inventory before replacing brief inputs..
  Rationale: Provider availability and model validation need one authoritative boundary; otherwise the UI would duplicate provider-specific behavior and cannot isolate failures.
  Honors: Success criteria requiring only available providers and models obtained from provider APIs..

- `dec_002` · 2026-10-24 · Epic Manager · **Refresh policy**
  Chose Use bounded on-demand caching with expiry or explicit refresh; do not build periodic background synchronization in the initial epic..
  Rationale: It avoids repeated API calls while keeping the first delivery small; durable scheduling adds operational cost without being required to validate briefs.
  Honors: The brief's suggestion that asynchronous refresh is optional, plus the frugal smallest-shippable-slice constraint..

- `dec_003` · 2026-10-24 · Epic Manager · **Configuration contract**
  Chose Select one provider and persist model defaults for every existing epic, feature, and task role; reject arbitrary model text for new or edited selections..
  Rationale: A shared provider matches the current brief contract while per-role models satisfy full-stack configuration and prevent invalid downstream values.
  Honors: Success criteria requiring model choice for the full agent stack..

- `dec_004` · 2026-10-24 · Epic Manager · **Compatibility**
  Chose Keep historical briefs readable without migration, while validating new or edited selections against current discovery..
  Rationale: Provider catalogs change; forcing migration is costly and could make prior artifacts unreadable, while validation still protects newly created downstream work.
  Honors: Core reliability without expanding scope into historical data migration..
## Amendment log

_(none)_
