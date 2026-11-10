import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const ui = require(join(root, "cascade/war_room/static/audit_status_ui.js"));

class Node {
  constructor(tag, ownerDocument) {
    this.tag = tag;
    this.ownerDocument = ownerDocument;
    this.children = [];
    this.className = "";
    this._text = "";
  }
  appendChild(child) { this.children.push(child); return child; }
  removeChild(child) { this.children.splice(this.children.indexOf(child), 1); }
  get firstChild() { return this.children[0] || null; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); }
}
const document = {
  createElement(tag) { return new Node(tag, document); },
  createTextNode(value) { const node = new Node("#text", document); node.textContent = value; return node; }
};
const container = new Node("div", document);

ui.render(container, {
  last_run: "2026-11-08T12:00:00Z",
  next_due: "2026-11-08T12:30:00Z",
  duration_seconds: 2.25,
  counts: {
    by_outcome: { healthy: 2, expected_wait: 0, proven_incident: 1, unavailable_evidence: 1 },
    by_tier: { task: { healthy: 2 }, feature: { proven_incident: 1 }, epic: { unavailable_evidence: 1 } }
  },
  incidents: [{
    work_id: "feat_001", failure_class: "stalled_owner", outcome: "claimed",
    owner: "feature_team:feat_001",
    evidence: { available: false, value: null },
    request: { state: "acknowledged", value: { operation: "resume_planning_owner" } },
    acknowledgement: { available: true, value: { worker: "health-audit-recovery" } },
    result: { available: false, value: null },
    retry: { claim_expires_at: "2026-11-08T12:05:00Z", next_reassessment_at: null, policy: { attempt_bound: 3 } },
    resume_action: { operation: "resume_planning_owner", owner: "feature_team:feat_001" }
  }],
  unavailable_evidence: [{ source: "orphan_delivery", reason: "unreadable" }]
});

const visible = container.textContent;
for (const expected of [
  "Last run", "Next due", "Duration", "Active incidents (1)", "feat_001",
  "Owner: feature_team:feat_001", "Evidence: Unavailable",
  "Request: acknowledged", "Acknowledgement: worker=health-audit-recovery",
  "Result: Pending", "Retry / cooldown", "Resume action: resume_planning_owner",
  "Unavailable evidence: orphan_delivery: unreadable"
]) assert.ok(visible.includes(expected), expected + " was not rendered\n" + visible);
assert.ok(!visible.includes("investigating"));

class Control {
  constructor() {
    this.disabled = false;
    this.textContent = "";
    this.classList = { toggle: (name, enabled) => { this.error = name === "error" && enabled; } };
    this.listeners = {};
  }
  addEventListener(name, listener) { this.listeners[name] = listener; }
}

async function exerciseAdmission(admission, expected) {
  const button = new Control();
  const status = new Control();
  let requests = 0;
  let resolveRequest;
  const request = new Promise((resolve) => { resolveRequest = resolve; });
  let refreshes = 0;
  const control = ui.bindRunControl({
    button,
    status,
    request() { requests += 1; return request; },
    refresh() { refreshes += 1; },
  });
  const first = control.submit();
  const duplicate = control.submit();
  assert.equal(button.disabled, true);
  assert.equal(requests, 1, "duplicate submission must be suppressed while pending");
  resolveRequest({ status: 202, body: { ok: true, status: admission } });
  await Promise.all([first, duplicate]);
  assert.ok(status.textContent.includes(expected), status.textContent);
  assert.ok(status.textContent.includes("pending"), "admission must not claim recovery");
  assert.equal(status.error, false);
  assert.equal(button.disabled, false);
  assert.equal(refreshes, 1);
}

await exerciseAdmission("admitted", "admitted");
await exerciseAdmission("coalesced", "already pending or running");

const unavailableButton = new Control();
const unavailableStatus = new Control();
const unavailable = ui.bindRunControl({
  button: unavailableButton,
  status: unavailableStatus,
  request() { return Promise.reject(new Error("health audit unavailable")); },
});
await unavailable.submit();
assert.equal(unavailableStatus.textContent, "health audit unavailable");
assert.equal(unavailableStatus.error, true);
assert.equal(unavailableButton.disabled, false);

ui.render(container, {
  investigations: [{work_id: 'task_034_005_001', owner_id: 'feat_034_005', reason: 'unknown_failure',
    status: 'reassess', reports: [{outcome: 'repair_requested', finding: 'Parent is investigating the blocker'}]}],
  agent_schedule: {next_due: 1800, last_error: {error: 'DeliveryUnavailable'}}
});
for (const expected of ['Agent investigations (1)', 'Parent is investigating the blocker', 'DeliveryUnavailable', 'Next agent review']) {
  assert.ok(container.textContent.includes(expected), expected);
}
