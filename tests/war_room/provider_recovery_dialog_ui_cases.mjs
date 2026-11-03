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

console.log("provider_recovery_dialog_ui_cases: ok");
