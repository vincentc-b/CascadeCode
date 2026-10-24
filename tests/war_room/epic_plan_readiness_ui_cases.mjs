import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const EpicPlanReadinessUi = require(
  join(repoRoot, "cascade/war_room/static/epic_plan_readiness_ui.js")
);

function createElement(tag) {
  const el = {
    tagName: tag.toUpperCase(),
    className: "",
    classList: {
      _classes: new Set(),
      add(name) {
        this._classes.add(name);
      },
      toggle() {},
    },
    children: [],
    attributes: {},
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    removeAttribute(name) {
      delete this.attributes[name];
    },
    getAttribute(name) {
      return this.attributes[name];
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    replaceChildren() {
      this.children = [];
    },
    querySelector() {
      return null;
    },
    addEventListener() {},
    disabled: false,
    hidden: false,
    textContent: "",
    title: "",
    dataset: {},
  };
  return el;
}

const document = { createElement };

const planning = {
  status: "planning",
  can_approve_plan: false,
  approve_disabled_reason: "missing_epic_manager_sign_off",
};

assert.equal(EpicPlanReadinessUi.planEntryStatusLabel(planning), "Planning in progress");
assert.match(
  EpicPlanReadinessUi.approvePlanDisabledReason(planning),
  /Epic Manager must sign off/
);

const ready = {
  status: "ready_for_review",
  can_approve_plan: true,
  approve_disabled_reason: null,
};
assert.equal(EpicPlanReadinessUi.planEntryStatusLabel(ready), "Ready for review");
assert.equal(EpicPlanReadinessUi.approvePlanDisabledReason(ready), null);

const statusEl = EpicPlanReadinessUi.createPlanEntryStatus(document, planning);
assert.ok(statusEl.className.includes("planning"));
assert.equal(statusEl.attributes["aria-label"], "Epic plan readiness: Planning in progress");
assert.ok(statusEl.children.some((c) => c.className === "epic-plan-readiness-indicator"));

const readyEl = EpicPlanReadinessUi.createPlanEntryStatus(document, ready);
assert.ok(readyEl.className.includes("ready"));
assert.ok(readyEl.children.some((c) => c.className === "epic-plan-readiness-ready-mark"));

const row = createElement("div");
EpicPlanReadinessUi.appendPlanEntryStatusToRow(document, row, planning);
assert.equal(row.children.length, 1);

const chrome = EpicPlanReadinessUi.renderPlanReadinessBar(document, planning, "epic_001");
assert.equal(chrome.approveButton.disabled, true);
assert.equal(chrome.approveButton.attributes["aria-disabled"], "true");
assert.ok(chrome.disabledReasonNote.textContent.includes("Epic Manager"));

EpicPlanReadinessUi.applyReadinessToPlanBar(chrome, document, ready, "epic_001");
assert.equal(chrome.approveButton.disabled, false);
assert.equal(chrome.approveButton.attributes["aria-disabled"], undefined);

console.log("epic_plan_readiness_ui_cases: ok");
