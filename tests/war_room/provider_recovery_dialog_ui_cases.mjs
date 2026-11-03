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

selection = recoveryUi.applyProviderChange(inventory, selection, "task", "codex");
assert.equal(selection.provider, "codex");
assert.equal(selection.models.swe, "manager");
assert.equal(selection.reasoning.swe, "");
assert.equal(selection.flex_mode, true);
selection = recoveryUi.applyModelChange(inventory, selection, "swe", "worker");
selection.reasoning.swe = "high";
selection.flex_mode = true;
assert.equal(recoveryUi.canSubmit(inventory, selection, "task"), true);
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

const empty = recoveryUi.statusMessage({ loading: false, providers: [] });
assert.match(empty.text, /No usable provider/);
assert.equal(empty.recoverable, true);

console.log("provider_recovery_dialog_ui_cases: ok");
