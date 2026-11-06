import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createElement } from "./plan_dom_fixture.mjs";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const DependencyStatusUi = require(
  join(repoRoot, "cascade/war_room/static/dependency_status_ui.js")
);

const document = { createElement };
const host = createElement("section");
host.replaceChildren = function () {
  this.children = [];
};

const historicalMessage = {
  author: "epic_manager",
  body: "Blocked by epic_036.",
  ts: "2026-11-06T09:00:00+00:00",
};
const messageElement = createElement("div");
const body = createElement("div");
body.className = "chat-body";
body.textContent = historicalMessage.body;
messageElement.appendChild(body);
DependencyStatusUi.appendHistoricalObservation(document, messageElement, historicalMessage);

assert.equal(body.textContent, "Blocked by epic_036.");
const historicalLabel = messageElement.children[1].children[0].textContent;
assert.match(historicalLabel, /^Historical transcript/);
assert.match(historicalLabel, /2026-11-06T09:00:00/);

const legacyElement = createElement("div");
const legacyMessage = {
  author: "epic_manager",
  body: "Document access denied, so epic_036 must still be blocked.",
};
DependencyStatusUi.appendHistoricalObservation(document, legacyElement, legacyMessage);
assert.equal(
  legacyElement.children[0].textContent,
  "Historical transcript · observation time unavailable"
);

const unmet = {
  observed_at: "2026-11-06T09:00:00+00:00",
  outcome: "dependency_unmet",
  explanation: "One or more declared dependencies are not complete.",
  dependencies: [{
    work_id: "epic_036",
    outcome: "dependency_unmet",
    explanation: "The dependency is not complete.",
  }],
};
DependencyStatusUi.renderCurrentSummary(document, host, unmet);
assert.equal(host.children[0].textContent, "Current dependency status");
assert.match(host.children[1].textContent, /not complete/);
assert.match(host.children[3].textContent, /^Observed at/);

const satisfied = {
  observed_at: "2026-11-06T10:00:00+00:00",
  outcome: "satisfied",
  explanation: "All declared dependencies are complete.",
  dependencies: [{
    work_id: "epic_036",
    outcome: "satisfied",
    explanation: "The dependency is complete.",
  }],
};
DependencyStatusUi.renderCurrentSummary(document, host, satisfied);

assert.match(host.children[1].textContent, /complete/);
assert.match(host.children[3].textContent, /2026-11-06T10:00:00/);
assert.equal(body.textContent, "Blocked by epic_036.");
assert.match(messageElement.children[1].children[0].textContent, /2026-11-06T09:00:00/);

const view = {
  epics: { "1_backlog": [], "2_active": [{ id: "epic_034", dependency_status: satisfied }], "3_completed": [] },
  features: { "1_backlog": [], "2_active": [], "3_completed": [] },
};
assert.equal(DependencyStatusUi.findRoomItem(view, "epic_034").dependency_status, satisfied);

console.log("dependency_status_ui_cases: ok");
