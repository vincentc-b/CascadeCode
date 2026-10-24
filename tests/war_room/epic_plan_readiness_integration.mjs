/**
 * Epic plan readiness UI integration (feat_015_002 / task_015_002_002).
 *
 * Covers disabled approval reasons, partial sign-off blocking, planning-to-ready
 * transition, reduced-motion-safe indicator, and stale approval rejection with
 * readiness refresh via initEpicPlanReadinessChrome.
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createElement } from "./plan_dom_fixture.mjs";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const staticDir = join(repoRoot, "cascade/war_room/static");

const EpicPlanReadinessUi = require(join(staticDir, "epic_plan_readiness_ui.js"));
const { initEpicPlanReadinessChrome } = require(join(staticDir, "plan_viewer.js"));

function enhanceElement(el) {
  const listeners = new Map();
  el.dataset = el.dataset || {};
  const baseGetAttribute = el.getAttribute.bind(el);
  el.getAttribute = (name) => {
    if (name === "id" && el.id) return el.id;
    return baseGetAttribute(name);
  };
  el.addEventListener = (type, handler) => {
    if (!listeners.has(type)) listeners.set(type, []);
    listeners.get(type).push(handler);
  };
  el.dispatchEvent = (type) => {
    for (const handler of listeners.get(type) || []) {
      handler({ type });
    }
  };
  el.replaceChildren = (...nodes) => {
    el.children = [];
    for (const node of nodes) {
      if (node) el.appendChild(node);
    }
  };
  if (typeof el.removeAttribute !== "function") {
    el.removeAttribute = (name) => {
      delete el.attributes[name];
    };
  }
  return el;
}

function documentShim() {
  const byId = new Map();
  return {
    getElementById(id) {
      return byId.get(id) || null;
    },
    createElement(tag) {
      return enhanceElement(createElement(tag));
    },
    register(id, el) {
      byId.set(id, el);
      return el;
    },
  };
}

function readiness(status, canApprove, disabledReason, signOffs = []) {
  return {
    status,
    can_approve_plan: canApprove,
    approve_disabled_reason: disabledReason,
    sign_offs: signOffs,
  };
}

const planningNone = readiness("planning", false, "missing_epic_manager_sign_off");
const planningManagerOnly = readiness(
  "planning",
  false,
  "missing_epic_architect_sign_off",
  ["epic_manager"]
);
const readyBoth = readiness("ready_for_review", true, null, ["epic_manager", "epic_architect"]);

function assertDisabledApprove(chrome, reasonSubstring) {
  assert.equal(chrome.approveButton.disabled, true);
  assert.equal(chrome.approveButton.getAttribute("aria-disabled"), "true");
  assert.ok(chrome.disabledReasonNote);
  assert.match(chrome.disabledReasonNote.textContent, new RegExp(reasonSubstring, "i"));
  const reasonId =
    chrome.disabledReasonNote.id || chrome.disabledReasonNote.getAttribute("id");
  assert.equal(reasonId, "epic-approve-disabled-reason-epic_001");
  assert.equal(chrome.approveButton.getAttribute("aria-describedby"), reasonId);
  const statusWrap = chrome.bar.querySelector(".epic-plan-readiness-status-planning");
  assert.ok(statusWrap, "expected planning status in bar");
  assert.equal(statusWrap.getAttribute("role"), "status");
  assert.match(statusWrap.getAttribute("aria-label"), /Planning in progress/);
}

function assertReadyApprove(chrome) {
  assert.equal(chrome.approveButton.disabled, false);
  assert.equal(chrome.approveButton.getAttribute("aria-disabled"), null);
  const statusWrap = chrome.bar.querySelector(".epic-plan-readiness-status-ready");
  assert.ok(statusWrap, "expected ready status in bar");
  assert.equal(statusWrap.getAttribute("role"), "status");
  assert.match(statusWrap.getAttribute("aria-label"), /Ready for review/);
  assert.ok(statusWrap.querySelector(".epic-plan-readiness-ready-mark"));
}

function tick() {
  return new Promise((resolve) => setImmediate(resolve));
}

// --- Disabled reason and planning-to-ready transition on the plan bar ---

const doc = documentShim();
globalThis.document = doc;

let chrome = EpicPlanReadinessUi.renderPlanReadinessBar(doc, planningNone, "epic_001");
assertDisabledApprove(chrome, "Epic Manager");

EpicPlanReadinessUi.applyReadinessToPlanBar(chrome, doc, planningManagerOnly, "epic_001");
assertDisabledApprove(chrome, "Epic Architect");

EpicPlanReadinessUi.applyReadinessToPlanBar(chrome, doc, readyBoth, "epic_001");
assertReadyApprove(chrome);

// --- Reduced motion: nonessential animation class omitted when user prefers reduce ---

const motionDoc = documentShim();
globalThis.matchMedia = (query) => ({
  matches: query === "(prefers-reduced-motion: reduce)",
  media: query,
});
const planningStatus = EpicPlanReadinessUi.createPlanEntryStatus(motionDoc, planningNone);
const indicator = planningStatus.children.find((c) =>
  String(c.className).includes("epic-plan-readiness-indicator")
);
assert.ok(indicator);
assert.ok(indicator.classList.contains("epic-plan-readiness-indicator-static"));

globalThis.matchMedia = () => ({ matches: false, media: "" });
const animatedStatus = EpicPlanReadinessUi.createPlanEntryStatus(motionDoc, planningNone);
const animatedIndicator = animatedStatus.children.find((c) =>
  String(c.className).includes("epic-plan-readiness-indicator")
);
assert.ok(animatedIndicator);
assert.equal(animatedIndicator.classList.contains("epic-plan-readiness-indicator-static"), false);

// --- Stale approval: error surfaced, plan retained, readiness refreshed ---

const integrationDoc = documentShim();
globalThis.document = integrationDoc;

const planBody = integrationDoc.register("plan-body", integrationDoc.createElement("div"));
planBody.textContent = "Canonical epic plan body must remain visible.";

const host = integrationDoc.register(
  "epic-plan-readiness-host",
  integrationDoc.createElement("div")
);

const staleError = "Epic plan is not ready for approval; refresh and sign off again.";
let docRefreshCalls = 0;

globalThis.fetch = (url, options) => {
  const path = String(url);
  if (path.includes("/api/approve_epic_plan") && options && options.method === "POST") {
    return Promise.resolve({
      ok: false,
      status: 409,
      statusText: "Conflict",
      text: () => Promise.resolve(JSON.stringify({ error: staleError })),
    });
  }
  if (path.includes("/api/doc/epic_001")) {
    docRefreshCalls += 1;
    return Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve({
          plan_readiness: planningManagerOnly,
        }),
    });
  }
  return Promise.reject(new Error("unexpected fetch: " + path));
};

globalThis.AbortController = class {
  constructor() {
    this.signal = {};
  }
  abort() {}
};

const epicId = "epic_001";
const mounted = initEpicPlanReadinessChrome(epicId, readyBoth, {
  EpicPlanReadinessUi,
});
assert.ok(mounted);
assert.ok(host.children.length > 0, "readiness chrome mounted in host");
assert.equal(planBody.textContent.includes("Canonical epic plan"), true);

const liveChrome = mounted.chrome;
assertReadyApprove(liveChrome);

liveChrome.approveButton.dispatchEvent("click");
await tick();
await tick();

assert.equal(liveChrome.approveButton.textContent, "Approve plan");
assert.equal(liveChrome.approveButton.classList.contains("approval-confirmed"), false);
assert.equal(liveChrome.errorElement.hidden, false);
assert.equal(liveChrome.errorElement.textContent, staleError);
assert.equal(liveChrome.errorElement.getAttribute("role"), "alert");
assert.ok(docRefreshCalls >= 1, "readiness refresh should call /api/doc after stale rejection");
assertDisabledApprove(liveChrome, "Epic Architect");
assert.equal(planBody.textContent.includes("Canonical epic plan"), true);

console.log("epic_plan_readiness_integration: ok");
