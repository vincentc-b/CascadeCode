import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const recoveryUi = require(join(
  repoRoot,
  "cascade/war_room/static/provider_recovery_dialog_ui.js"
));

const inventory = {
  loading: false,
  default_provider: "codex",
  providers: [
    {
      id: "codex",
      display_name: "Codex",
      supports_flex_mode: true,
      models: [
        { id: "manager", display_name: "Manager" },
        {
          id: "worker",
          display_name: "Worker",
          reasoning: {
            default_level: "medium",
            override_levels: ["high"],
            default_only: false,
          },
        },
      ],
    },
    {
      id: "cursor",
      display_name: "Cursor",
      supports_flex_mode: false,
      models: [{ id: "composer", display_name: "Composer" }],
    },
  ],
  refresh: { failed: false },
};

assert.deepEqual(recoveryUi.rolesForTier("epic"), ["epic_manager", "epic_architect"]);
assert.deepEqual(recoveryUi.rolesForTier("feature"), ["feature_lead", "feature_architect"]);
assert.deepEqual(recoveryUi.rolesForTier("task"), ["swe"]);
assert.deepEqual(recoveryUi.rolesForTier("unknown"), []);

const unavailableSaved = {
  provider: "retired",
  models: { swe: "old-worker" },
  reasoning: { swe: "max" },
  flex_mode: true,
};
let selection = recoveryUi.initialSelection(inventory, unavailableSaved, "task");
assert.equal(selection.provider, "retired");
assert.equal(selection.models.swe, "old-worker");
assert.equal(selection.reasoning.swe, "max");
assert.equal(selection.flex_mode, true);
assert.equal(recoveryUi.canSubmit(inventory, selection, "task"), false);

const unavailableModel = {
  provider: "codex",
  models: { swe: "retired-worker" },
  reasoning: { swe: "high" },
  flex_mode: false,
};
selection = recoveryUi.initialSelection(inventory, unavailableModel, "task");
assert.equal(selection.provider, "codex");
assert.equal(selection.models.swe, "retired-worker");
assert.equal(recoveryUi.canSubmit(inventory, selection, "task"), false);

selection = recoveryUi.applyProviderChange(inventory, selection, "task", "codex");
assert.equal(selection.provider, "codex");
assert.equal(selection.models.swe, "manager");
assert.equal(selection.reasoning.swe, "");
assert.equal(selection.flex_mode, false);
selection = recoveryUi.applyModelChange(inventory, selection, "swe", "worker");
selection.reasoning.swe = "high";
selection.flex_mode = true;
assert.equal(recoveryUi.canSubmit(inventory, selection, "task"), true);
selection.reasoning.swe = "unsupported";
assert.equal(recoveryUi.canSubmit(inventory, selection, "task"), false);
selection.reasoning.swe = "high";
assert.deepEqual(recoveryUi.buildPayload(selection, "task"), {
  provider: "codex",
  models: { swe: "worker" },
  flex_mode: true,
  reasoning: { swe: "high" },
});

selection = recoveryUi.applyProviderChange(inventory, selection, "task", "cursor");
assert.equal(selection.models.swe, "composer");
assert.equal(selection.reasoning.swe, "");
assert.equal(selection.flex_mode, false);
assert.equal(recoveryUi.canSubmit(inventory, selection, "task"), true);

selection.reasoning.swe = "high";
assert.equal(
  recoveryUi.canSubmit(inventory, selection, "task"),
  false,
  "reasoning is invalid when the selected model does not expose it"
);

let epicSelection = recoveryUi.initialSelection(inventory, null, "epic");
epicSelection = recoveryUi.applyProviderChange(
  inventory,
  epicSelection,
  "epic",
  "cursor"
);
assert.deepEqual(epicSelection.models, {
  epic_manager: "composer",
  epic_architect: "composer",
});
assert.deepEqual(recoveryUi.buildPayload(epicSelection, "epic"), {
  provider: "cursor",
  models: { epic_manager: "composer", epic_architect: "composer" },
  flex_mode: false,
  reasoning: {},
});

const empty = recoveryUi.statusMessage({ loading: false, providers: [] });
assert.match(empty.text, /No usable provider/);
assert.equal(empty.recoverable, true);

const loading = recoveryUi.statusMessage({ loading: true, providers: [] });
assert.match(loading.text, /Loading available providers/);
assert.equal(loading.recoverable, false);

const failedRefresh = recoveryUi.statusMessage({
  loading: false,
  providers: [],
  refresh: { failed: true },
});
assert.match(failedRefresh.text, /Could not refresh model inventory/);
assert.equal(failedRefresh.error, true);
assert.equal(failedRefresh.recoverable, true);

const blockedBatch = {
  action: "feature_dispatch",
  message: "The selected model is not offered.",
  selection_fingerprint: "fingerprint-1",
  inventory_freshness: { stale: false, fetched_at: 100, age_seconds: 4.4 },
  checks: [
    {
      role: "feature_lead",
      outcome: "supported",
      provider: "codex",
      model_id: "manager",
      reasoning_effective: "high",
      effective_flex_mode: false,
      message: "Available.",
      document_path: "docs/features/feat_001.md",
      document_revision: "rev-1",
    },
    {
      role: "swe",
      outcome: "unsupported",
      provider: "codex",
      model_id: "future-worker",
      message: "The selected model is not offered.",
      document_path: "docs/tasks/task_001.md",
      document_revision: "rev-2",
    },
  ],
};
const diagnostic = recoveryUi.diagnosticView(blockedBatch);
assert.equal(diagnostic.action, "feature dispatch");
assert.equal(diagnostic.checks.length, 2);
assert.equal(diagnostic.checks[0].role, "Feature Lead");
assert.match(diagnostic.checks[0].selection, /Flex off/);
assert.match(diagnostic.checks[1].provenance, /rev-2/);
assert.equal(
  recoveryUi.failureBatch(null, { failed_diagnostics: blockedBatch }),
  blockedBatch
);
const combined = recoveryUi.failureBatch({
  message: "Approval saved; two launches were blocked.",
  dispatch_refusals: [
    { work_id: "feat_001", preflight: blockedBatch },
    { work_id: "feat_002", preflight: Object.assign({}, blockedBatch, { checks: [blockedBatch.checks[1]] }) },
  ],
});
assert.equal(combined.checks.length, 3);
assert.equal(combined.checks[0].work_id, "feat_001");
assert.equal(combined.checks[2].work_id, "feat_002");
assert.equal(recoveryUi.diagnosticView(combined).checks[2].role, "SWE (feat_002)");

assert.deepEqual(recoveryUi.readinessSummary({
  outcome: "supported",
  message: "Available.",
  inventory_freshness: { stale: false, fetched_at: 100, age_seconds: 2 },
}), {
  kind: "ready",
  label: "Configuration ready",
  detail: "Available.",
  freshness: "Inventory freshness: current (2s old)",
});
assert.match(
  recoveryUi.readinessSummary({
    outcome: "transient",
    inventory_freshness: { stale: true, fetched_at: null },
  }).label,
  /unknown · stale/
);
assert.equal(
  recoveryUi.partialOutcome({
    dispatch_pending: true,
    approval_committed: true,
    dispatch_outcome: { launched: ["feat_001"], not_launched: ["feat_002"] },
  }),
  "Approval was saved. Launched: feat_001. Not launched: feat_002."
);

console.log("provider_recovery_dialog_ui_cases: ok");
