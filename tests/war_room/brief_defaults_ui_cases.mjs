import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const {
  initialSelection,
  applyProviderChange,
  providerSupportsFlexMode,
  normalizeFlexMode,
  applyRoleModelChange,
  canSubmitBrief,
  buildSubmitPayload,
  reasoningChoices,
  briefStatusMessage,
} = require(join(repoRoot, "cascade/war_room/static/brief_defaults_ui.js"));

const inventory = {
  availability: "partial",
  loading: false,
  default_provider: "codex",
  providers: [
    {
      id: "codex",
      display_name: "Codex",
      supports_flex_mode: true,
      models: [
        { id: "gpt-manager", display_name: "Manager" },
        { id: "gpt-architect", display_name: "Architect" },
        { id: "gpt-feature-lead", display_name: "Feature lead" },
        { id: "gpt-feature-architect", display_name: "Feature architect" },
        {
          id: "gpt-swe",
          display_name: "SWE",
          reasoning: {
            default_level: "medium",
            override_levels: ["low", "high"],
            default_only: false,
          },
        },
      ],
    },
    {
      id: "cursor",
      display_name: "Cursor",
      supports_flex_mode: false,
      models: [{ id: "composer-2.5", display_name: "Composer 2.5" }],
    },
  ],
  refresh: { forced: false, failed: false, error: null },
};

const template = {
  provider: "codex",
  providers: ["codex", "cursor"],
  models: {
    epic_manager: "gpt-manager",
    epic_architect: "gpt-architect",
    feature_lead: "gpt-feature-lead",
    feature_architect: "gpt-feature-architect",
    swe: "gpt-swe",
  },
  provider_models: {
    codex: {
      epic_manager: "gpt-manager",
      epic_architect: "gpt-architect",
      feature_lead: "gpt-feature-lead",
      feature_architect: "gpt-feature-architect",
      swe: "gpt-swe",
    },
    cursor: {
      epic_manager: "composer-2.5",
      epic_architect: "composer-2.5",
      feature_lead: "composer-2.5",
      feature_architect: "composer-2.5",
      swe: "composer-2.5",
    },
  },
  suggestions: {},
  tracking_ready: true,
};

assert.equal(providerSupportsFlexMode(inventory, "codex"), true);
assert.equal(providerSupportsFlexMode(inventory, "cursor"), false);
assert.equal(normalizeFlexMode(inventory, "cursor", true, false), false);

let selection = initialSelection(inventory, template);
assert.equal(selection.provider, "codex");
assert.equal(selection.models.epic_manager, "gpt-manager");
assert.equal(selection.models.swe, "gpt-swe");
assert.equal(selection.flex_mode, true);
assert.equal(buildSubmitPayload({}, selection).flex_mode, true);

selection = applyProviderChange(inventory, template, selection, "cursor");
assert.equal(selection.provider, "cursor");
assert.equal(selection.models.epic_manager, "composer-2.5");
assert.equal(selection.reasoning.swe, "");
assert.equal(selection.flex_mode, false);

selection = applyProviderChange(inventory, template, selection, "codex");
assert.equal(selection.models.swe, "gpt-swe");
assert.equal(selection.flex_mode, false);
selection.reasoning.swe = "high";
assert.equal(selection.reasoning.swe, "high");
selection.reasoning.swe = "turbo";
assert.equal(canSubmitBrief(inventory, selection, true), false);
selection.reasoning.swe = "high";

const sweModel = inventory.providers[0].models[4];
const choices = reasoningChoices(sweModel);
assert.ok(choices);
assert.equal(choices[0].value, "");
assert.deepEqual(
  choices.map((item) => item.value),
  ["", "low", "high"]
);

assert.equal(canSubmitBrief(inventory, selection, true), true);
assert.equal(canSubmitBrief(inventory, selection, false), false);
assert.equal(
  canSubmitBrief({ loading: false, providers: [] }, selection, true),
  false
);

const payload = buildSubmitPayload(
  { title: "T", intent: "I", success_criteria: "S", constraints: "" },
  selection
);
assert.equal(payload.provider, "codex");
assert.equal(payload.models.swe, "gpt-swe");
assert.equal(payload.reasoning.swe, "high");
assert.equal(payload.flex_mode, false);

const optedOutTemplate = Object.assign({}, template, {
  saved: {
    provider: "codex",
    models: Object.assign({}, template.models),
    reasoning: {},
    flex_mode: false,
  },
});
const optedOut = initialSelection(inventory, optedOutTemplate, { preserveSaved: true });
assert.equal(optedOut.flex_mode, false);

const savedTarget = {
  epic_id: "epic_024",
  source_path: "docs/epics/1_backlog/epic_024_edit_brief.md",
  source_revision: "old-revision",
  provider: "cursor",
  models: { swe: "composer-2.5" },
  reasoning: { swe: "low" },
  flex_mode: false,
};
const editPayload = require("../../cascade/war_room/static/brief_defaults_ui.js").buildEditSubmitPayload(
  { title: "Edited", intent: "New intent", additional_markdown: "## Extra\nText" },
  selection,
  savedTarget
);
assert.equal(editPayload.epic_id, "epic_024");
assert.equal(editPayload.source_revision, "old-revision");
assert.equal(editPayload.provider, "codex");
assert.equal(editPayload.models.swe, "gpt-swe");
assert.equal(editPayload.reasoning.swe, "high");
assert.equal(editPayload.flex_mode, false);
assert.equal(editPayload.additional_markdown, "## Extra\nText");

const emptyStatus = briefStatusMessage({ loading: false, providers: [] }, true);
assert.match(emptyStatus.text, /No usable provider/);
assert.equal(emptyStatus.error, true);

console.log("brief_defaults_ui_cases: ok");
