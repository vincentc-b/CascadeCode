/** Focused flex-mode editor flow against a live War Room server. */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const BriefDefaultsUi = require(
  join(repoRoot, "cascade/war_room/static/brief_defaults_ui.js")
);
const base = process.env.WAR_ROOM_BASE;
assert.ok(base, "WAR_ROOM_BASE is required");

async function get(path) {
  const response = await fetch(`${base}${path}`);
  const body = await response.text();
  assert.equal(response.status, 200, body);
  return JSON.parse(body);
}

async function post(path, payload) {
  const response = await fetch(`${base}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const body = await response.text();
  assert.equal(response.status, 201, body);
  return JSON.parse(body);
}

function renderControl(inventory, selection) {
  const wrap = { hidden: true };
  const checkbox = { checked: false, disabled: true, onchange: null };
  BriefDefaultsUi.renderFlexModeControl(wrap, checkbox, inventory, selection);
  return { wrap, checkbox };
}

const inventory = await get("/api/brief/inventory");
const template = Object.assign(await get("/api/brief/template"), { provider: "codex" });

let selection = BriefDefaultsUi.initialSelection(inventory, template);
let control = renderControl(inventory, selection);
assert.equal(control.wrap.hidden, false, "capable provider shows flex control");
assert.equal(control.checkbox.checked, true, "new brief defaults flex on");

control.checkbox.checked = false;
control.checkbox.onchange();
assert.equal(selection.flex_mode, false, "checkbox updates the submitted field");

const form = {
  title: "Flex editor system test",
  intent: "Exercise the flex editor flow.",
  success_criteria: "The persisted field follows the UI selection.",
  constraints: "",
};
const submitted = BriefDefaultsUi.buildSubmitPayload(form, selection);
assert.equal(submitted.flex_mode, false);
const created = await post("/api/briefs", submitted);

const reopenedTemplate = await get(
  `/api/brief/template?epic_id=${encodeURIComponent(created.epic_id)}`
);
selection = BriefDefaultsUi.initialSelection(inventory, reopenedTemplate, {
  preserveSaved: true,
});
control = renderControl(inventory, selection);
assert.equal(control.wrap.hidden, false);
assert.equal(control.checkbox.checked, false, "reopen preserves explicit opt-out");

selection = BriefDefaultsUi.applyProviderChange(
  inventory,
  reopenedTemplate,
  selection,
  "cursor"
);
control = renderControl(inventory, selection);
assert.equal(control.wrap.hidden, true, "unsupported provider hides flex control");
assert.equal(selection.flex_mode, false, "unsupported provider normalizes flex off");

selection = BriefDefaultsUi.applyProviderChange(
  inventory,
  reopenedTemplate,
  selection,
  "codex"
);
control = renderControl(inventory, selection);
assert.equal(control.wrap.hidden, false, "capable provider shows flex control again");
assert.equal(control.checkbox.checked, false, "normalized form value remains off");

console.log("brief_flex_mode_browser_flow: ok");
