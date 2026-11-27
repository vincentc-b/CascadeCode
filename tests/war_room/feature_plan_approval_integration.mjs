import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createElement } from "./plan_dom_fixture.mjs";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const { initFeaturePlanApprovalChrome } = require(
  join(repoRoot, "cascade/war_room/static/plan_viewer.js")
);

function enhance(el) {
  const listeners = new Map();
  el.addEventListener = (type, handler) => {
    if (!listeners.has(type)) listeners.set(type, []);
    listeners.get(type).push(handler);
  };
  el.dispatchEvent = (event) => {
    const value = typeof event === "string" ? { type: event } : event;
    for (const handler of listeners.get(value.type) || []) handler(value);
  };
  el.replaceChildren = (...nodes) => {
    el.children = [];
    nodes.forEach((node) => node && el.appendChild(node));
  };
  return el;
}

function documentShim() {
  const byId = new Map();
  return {
    createElement(tag) { return enhance(createElement(tag)); },
    getElementById(id) { return byId.get(id) || null; },
    register(id, el) { byId.set(id, el); return el; },
  };
}

function tick() {
  return new Promise((resolve) => setImmediate(resolve));
}

const context = {
  owner_work_id: "feat_001",
  target_repository_key: "target-fixture",
  plan_revision: "a".repeat(40),
  review_unit_id: "review-current",
  reviewed_tuple_digest: "b".repeat(64),
  accepted_baseline_generation: 7,
};
const pending = {
  approved: false,
  blockers: ["not_approved", "unmet_deps:feat_000"],
  approval: {
    result: "approval_required",
    state: "unapproved",
    eligibility: "eligible_waiting",
    eligible: true,
    affected_work_ids: ["feat_001", "feat_000"],
  },
  explanation: {
    reasons: [
      { code: "dependency_unmet", affected_work_ids: ["feat_000"] },
      { code: "not_approved", affected_work_ids: ["feat_001"] },
    ],
  },
};
const approvedWaiting = {
  ...pending,
  approved: true,
  blockers: ["unmet_deps:feat_000"],
  approval: { ...pending.approval, result: "approved", state: "approved" },
  explanation: {
    reasons: [{ code: "dependency_unmet", affected_work_ids: ["feat_000"] }],
  },
};

globalThis.AbortSignal = { timeout() { return {}; } };
const doc = documentShim();
globalThis.document = doc;
const host = doc.register("epic-plan-readiness-host", doc.createElement("div"));

// Missing reviewed evidence leaves a distinct, actionable disabled control.
let mounted = initFeaturePlanApprovalChrome("feat_001", pending, {});
assert.equal(mounted.approveButton.disabled, true);
assert.equal(mounted.approveButton.textContent, "Approve feature");
assert.match(host.querySelector(".feature-plan-approval-scope").textContent, /current reviewed scope|architecture review/i);

// One gesture submits the exact displayed tuple and remains disabled while slow.
let resolvePost;
let posts = [];
globalThis.fetch = (url, options) => {
  if (options && options.method === "POST") {
    posts.push(JSON.parse(options.body));
    return new Promise((resolve) => { resolvePost = resolve; });
  }
  return Promise.resolve({
    ok: true,
    json: async () => ({
      meta: { id: "feat_001", status: "backlog" },
      feature_readiness: approvedWaiting,
      paired_review: { approval_context: context },
    }),
  });
};
mounted = initFeaturePlanApprovalChrome("feat_001", pending, { reviewContext: context });
assert.match(host.querySelector(".feature-plan-approval-scope").textContent, new RegExp(context.review_unit_id));
mounted.approveButton.dispatchEvent({ type: "click" });
host.querySelector(".feature-plan-approval-button").dispatchEvent({ type: "click" });
assert.equal(posts.length, 1);
assert.deepEqual(posts[0], { id: "feat_001", review_context: context });
assert.equal(host.querySelector(".feature-plan-approval-button").disabled, true);
assert.equal(host.querySelector(".feature-plan-approval-status").getAttribute("role"), "status");

resolvePost({
  ok: true,
  text: async () => JSON.stringify({
    ok: true,
    approval_result: "approved",
    approval_state: "approved",
    approval_explanation: {
      code: "approval_saved_waiting",
      message: "Approval saved; predecessor completion is still required.",
    },
    affected_work_ids: ["feat_001", "feat_000"],
    execution_state: "waiting",
  }),
});
await tick();
await tick();
const waitingStatus = host.querySelector(".feature-plan-approval-status").textContent;
assert.match(waitingStatus, /approval is current|execution is waiting/i);
assert.match(waitingStatus, /dependency_unmet/);
assert.match(waitingStatus, /feat_001, feat_000/);
assert.equal(host.querySelector(".feature-plan-approval-button").textContent, "Approved");

// Explicit HTTP refusal remains visible across a later unapproved GET.
let getCalls = 0;
globalThis.fetch = async (url, options) => {
  if (options && options.method === "POST") {
    return {
      ok: false,
      status: 409,
      statusText: "Conflict",
      text: async () => JSON.stringify({
        approval_result: "refused",
        approval_state: "unapproved",
        approval_explanation: { code: "provider_preflight_refused", message: "Select a supported provider." },
        affected_work_ids: ["feat_001"],
        execution_state: "unknown",
      }),
    };
  }
  getCalls += 1;
  return { ok: true, json: async () => ({ meta: { status: "backlog" }, feature_readiness: pending, paired_review: { approval_context: context } }) };
};
mounted = initFeaturePlanApprovalChrome("feat_001", pending, { reviewContext: context });
mounted.approveButton.dispatchEvent({ type: "click" });
await tick();
assert.match(host.querySelector(".feature-plan-approval-status").textContent, /Select a supported provider/);
assert.equal(host.querySelector(".feature-plan-approval-status").getAttribute("role"), "alert");
await mounted.refreshCanonical(mounted.state.observation, false);
assert.equal(getCalls, 1);
assert.match(host.querySelector(".feature-plan-approval-status").textContent, /Select a supported provider/);

// A stale reviewed tuple is removed and cannot be retried unseen.
globalThis.fetch = async () => ({
  ok: false,
  status: 409,
  statusText: "Conflict",
  text: async () => JSON.stringify({
    approval_result: "refused",
    approval_state: "stale",
    approval_explanation: { code: "stale_review_context", message: "The displayed review tuple is stale." },
    affected_work_ids: ["feat_001"],
    execution_state: "unknown",
  }),
});
mounted = initFeaturePlanApprovalChrome("feat_001", pending, { reviewContext: context });
mounted.approveButton.dispatchEvent({ type: "click" });
await tick();
assert.equal(host.querySelector(".feature-plan-approval-button").disabled, true);
assert.equal(host.querySelector(".feature-plan-approval-button").textContent, "Approve feature");
assert.match(host.querySelector(".feature-plan-approval-scope").textContent, /Complete the architecture review/);

// A disconnect is unconfirmed until canonical evidence permits a safe retry.
globalThis.fetch = async (url, options) => {
  if (options && options.method === "POST") throw new Error("connection lost");
  return { ok: true, json: async () => ({ meta: { status: "backlog" }, feature_readiness: pending, paired_review: { approval_context: context } }) };
};
mounted = initFeaturePlanApprovalChrome("feat_001", pending, { reviewContext: context });
mounted.approveButton.dispatchEvent({ type: "click" });
await tick();
await tick();
assert.equal(host.querySelector(".feature-plan-approval-button").textContent, "Retry approval");
assert.equal(host.querySelector(".feature-plan-approval-button").disabled, false);
assert.match(host.querySelector(".feature-plan-approval-status").textContent, /unconfirmed/i);

console.log("feature_plan_approval_integration: ok");
