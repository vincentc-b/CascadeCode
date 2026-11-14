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
    this.listeners = {};
    this.open = false;
  }
  appendChild(child) { this.children.push(child); return child; }
  removeChild(child) { this.children.splice(this.children.indexOf(child), 1); }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  dispatch(name, event) { return this.listeners[name] && this.listeners[name](event); }
  get firstChild() { return this.children[0] || null; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); }
}
const document = {
  createElement(tag) { return new Node(tag, document); },
  createTextNode(value) { const node = new Node("#text", document); node.textContent = value; return node; }
};
const container = new Node("div", document);

let coverageRequests = 0;
let requestedCursor = "not-called";
ui.render(container, {
  snapshot: {state: "ready", epoch: "epoch-one"},
  receipt: {
    last_completed_at: "2026-11-08T12:00:00Z",
    next_scheduled_at: "2026-11-08T12:30:00Z"
  },
  last_run: "2026-11-08T12:00:00Z",
  next_due: "2026-11-08T12:30:00Z",
  duration_seconds: 2.25,
  counts: {
    by_outcome: { healthy: 2, expected_wait: 0, proven_incident: 1, unavailable_evidence: 1 },
    by_tier: { task: { healthy: 2 }, feature: { proven_incident: 1 }, epic: { unavailable_evidence: 1 } }
  },
  current: {complete: false, next_cursor: "more-current", rows: [{
    work_id: "feat_009", failure_class: "stalled_owner", verification_status: "proven_incident",
    owner: "feature_team:feat_001",
    reason: "Later authoritative blocker <img src=x onerror=alert(1)>",
    occurred_at: "2026-11-08T11:50:00Z", last_attempted_at: "2026-11-08T11:55:00Z",
    last_verified_at: "2026-11-08T12:00:00Z", fresh_until: "2026-11-08T13:00:00Z",
    next_attempt_at: "2026-11-08T12:15:00Z", provenance: {next_action: "Retry safely <script>bad()</script>"},
    source_ref: {store: "action_recovery", row_key: "current-later", incident_history_ordinal: 3}
  }]},
  coverage: {by_status: {pending: 2, stale: 1, unverifiable: 1}},
  incidents: [{work_id: "legacy_alias_must_not_render"}],
  investigation_snapshot: {state: "available", published_at: "2026-11-08T12:00:00Z"},
  investigations: [{
    work_id: "task_009", owner_id: "feat_009", reason: "unknown_failure",
    source: {case_id: "case-9", request_id: "request-9"},
    request: {state: "delivered", delivered_at: "2026-11-08T11:57:00Z"},
    acknowledgement: {state: "acknowledged", acknowledged_at: "2026-11-08T11:58:00Z"},
    latest_report: {outcome: "reported_fixed", reported_at: "2026-11-08T11:59:00Z",
      finding: "Reported only; <b>not verified</b>", references: ["ref:<unsafe>"]},
    pending_reassessment: {pending: true, next_at: "2026-11-08T12:10:00Z"}
  }],
  unavailable_evidence: [{ source: "orphan_delivery", reason: "unreadable" }]
}, {
  async loadCoverage(cursor) {
    coverageRequests += 1;
    requestedCursor = cursor;
    return {state: "ready", page: {complete: false, next_cursor: "coverage-next", rows: [
      {work_id: "task_009", owner: "feat_009", verification_status: "pending", reason: "timeout",
        source_ref: {store: "orphan_delivery", row_key: "first<unsafe>"}},
      {work_id: "task_009", owner: "feat_009", verification_status: "stale", reason: "timeout",
        source_ref: {store: "action_recovery", row_key: "second"}},
      {work_id: null, owner: null, verification_status: "unverifiable", reason: "legacy reason",
        source_ref: {store: "remediation_dispositions", row_key: "third"}}
    ]}};
  }
});

const visible = container.textContent;
for (const expected of [
  "Last run", "Next due", "Duration", "VERIFIED current incidents (1)", "feat_009",
  "Owner: feature_team:feat_001", "Impact / reason: Later authoritative blocker",
  "Occurred", "Last attempted", "Last verified", "Freshness: fresh until", "Next attempt", "Next action",
  "Source: action_recovery / current-later / incident 3", "Additional VERIFIED current incidents",
  "Coverage: pending 2 · stale 1 · unverifiable 1", "Last completed check", "Next scheduled check",
  "Investigation request: case case-9 · request request-9", "Delivery: delivered",
  "Acknowledgement: acknowledged", "Latest reported outcome: reported_fixed",
  "Unavailable evidence: orphan_delivery: unreadable"
]) assert.ok(visible.includes(expected), expected + " was not rendered\n" + visible);
assert.ok(!visible.includes("legacy_alias_must_not_render"));
assert.equal(coverageRequests, 0, "collapsed coverage must not fetch details");
const disclosure = container.children.find((child) => child.className === "audit-coverage-disclosure");
assert.ok(disclosure, "coverage disclosure missing");
disclosure.open = true;
await disclosure.dispatch("toggle");
await new Promise((resolve) => setTimeout(resolve, 0));
assert.equal(coverageRequests, 1);
assert.equal(requestedCursor, null);
for (const expected of ["Work task_009 (2)", "Reason legacy reason (1)",
  "Source: orphan_delivery / first<unsafe>", "Source: action_recovery / second",
  "Load next coverage page"]) assert.ok(container.textContent.includes(expected), expected);
assert.equal(container.children.some((child) => child.tag === "img" || child.tag === "script"), false);

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
  snapshot: {state: "ready"},
  current: {complete: true, rows: []},
  coverage: {by_status: {verified: 2}},
});
assert.ok(container.textContent.includes("No VERIFIED current incidents"));
assert.ok(!container.textContent.includes("coverage incomplete"));
ui.render(container, {
  snapshot: {state: "ready"},
  current: {complete: true, rows: []},
  coverage: {by_status: {pending: 1}}
});
assert.ok(container.textContent.includes("No VERIFIED current incidents; coverage incomplete."));
ui.render(container, {
  snapshot: {state: "pending", reason: "pointer_malformed"},
  current: {rows: []}, coverage: {by_status: {}},
  failure: {code: "snapshot_corrupt", next_action: "Run another check"}
});
assert.ok(container.textContent.includes("No VERIFIED current incidents; coverage incomplete."));
assert.ok(container.textContent.includes("Snapshot: pending · pointer_malformed"));
assert.ok(container.textContent.includes("Audit failure: code=snapshot_corrupt"));

function findClass(node, className) {
  if (node.className === className) return node;
  for (const child of node.children) {
    const found = findClass(child, className);
    if (found) return found;
  }
  return null;
}

function findName(node, name) {
  if (node.name === name) return node;
  for (const child of node.children) {
    const found = findName(child, name);
    if (found) return found;
  }
  return null;
}

const historyState = {};
const historyRequests = [];
let historyResponseEpoch = "epoch-history";
function historyOptions() {
  return {
    state: historyState,
    loadCoverage() { return Promise.resolve({state: "ready", page: {rows: [], complete: true}}); },
    loadHistory(cursor, filters) {
      historyRequests.push({cursor, filters});
      return Promise.resolve({state: "ready", page: {
        epoch: historyResponseEpoch, complete: false, reason: "limit", next_cursor: "opaque-next", rows: [{
          work_id: "task_044", owner: "feature_team:feat_044", verification_status: "unverifiable",
          occurred_at: "2026-11-14T10:00:00Z", last_attempted_at: "2026-11-14T10:05:00Z",
          last_verified_at: "2026-11-14T10:10:00Z", reason: "legacy record <unsafe>",
          source_ref: {store: "action_recovery", row_key: "row<unsafe>"},
          provenance: {legacy: true, note: "reported_fixed is not resolution <script>"}
        }]
      }});
    }
  };
}
ui.render(container, {snapshot: {state: "ready", epoch: "epoch-history"}, current: {rows: []}, coverage: {by_status: {}}}, historyOptions());
let historyDisclosure = findClass(container, "audit-history-disclosure");
assert.ok(historyDisclosure, "history disclosure missing");
assert.equal(historyDisclosure.open, false);
assert.equal(historyRequests.length, 0, "collapsed history must not fetch");
historyDisclosure.open = true;
await historyDisclosure.dispatch("toggle");
await new Promise((resolve) => setImmediate(resolve));
assert.equal(historyRequests.length, 1);
assert.equal(historyRequests[0].cursor, null);
for (const expected of [
  "Occurred: ", "Last attempted: ", "Last verified: ",
  "Source: action_recovery / row<unsafe>", "Legacy provenance: legacy=true",
  "Unverifiable previous attempt", "More matching history is available", "Reason: limit",
  "Load next history page"
]) assert.ok(container.textContent.includes(expected), expected + " missing from history");
assert.equal(container.children.some((child) => child.tag === "script"), false);

ui.render(container, {snapshot: {state: "ready", epoch: "epoch-history"}, current: {rows: []}, coverage: {by_status: {}}}, historyOptions());
historyDisclosure = findClass(container, "audit-history-disclosure");
assert.equal(historyDisclosure.open, true, "history disclosure survives status refresh");
assert.ok(container.textContent.includes("task_044"), "loaded history survives status refresh");

historyResponseEpoch = "epoch-new";
ui.render(container, {snapshot: {state: "ready", epoch: "epoch-new"}, current: {rows: []}, coverage: {by_status: {}}}, historyOptions());
await new Promise((resolve) => setImmediate(resolve));
assert.ok(container.textContent.includes("restarted from the first page"), "epoch restart must be visible");

const raceContainer = new Node("div", document);
const raceState = {};
const pendingHistory = [];
const raceOptions = {
  state: raceState,
  loadCoverage() { return Promise.resolve({state: "ready", page: {rows: [], complete: true}}); },
  loadHistory(cursor, filters) {
    let resolve;
    let reject;
    const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
    pendingHistory.push({cursor, filters, resolve, reject});
    return promise;
  }
};
ui.render(raceContainer, {snapshot: {state: "ready", epoch: "race-one"}, current: {rows: []}, coverage: {by_status: {}}}, raceOptions);
const raceDisclosure = findClass(raceContainer, "audit-history-disclosure");
raceDisclosure.open = true;
raceDisclosure.dispatch("toggle");
assert.equal(pendingHistory.length, 1);
findName(raceDisclosure, "workId").value = "task_new";
findName(raceDisclosure, "owner").value = "feature_team:new";
findName(raceDisclosure, "status").value = "unverifiable";
findClass(raceDisclosure, "audit-history-filters").dispatch("submit", {preventDefault() {}});
assert.equal(pendingHistory.length, 1, "new filters wait for the active detail request");
pendingHistory[0].resolve({state: "ready", page: {epoch: "race-one", complete: true, rows: [{work_id: "task_old"}]}});
await new Promise((resolve) => setImmediate(resolve));
assert.equal(pendingHistory.length, 2);
assert.equal(pendingHistory[1].cursor, null);
assert.equal(pendingHistory[1].filters.work_id, "task_new");
assert.equal(pendingHistory[1].filters.owner, "feature_team:new");
assert.equal(pendingHistory[1].filters.status, "unverifiable");
pendingHistory[1].resolve({state: "ready", page: {epoch: "race-one", complete: false, reason: "limit", next_cursor: "opaque-race", rows: [{
  work_id: "task_new", verification_status: "unverifiable"
}]}});
await new Promise((resolve) => setImmediate(resolve));
assert.ok(raceContainer.textContent.includes("task_new"));
assert.ok(!raceContainer.textContent.includes("task_old"), "stale filter reply must not render");
findClass(raceContainer, "btn-secondary audit-history-more").dispatch("click");
assert.equal(pendingHistory.length, 3);
pendingHistory[2].reject(Object.assign(new Error("Conflict"), {body: {
  restart: true, reason: "epoch_changed", epoch: "race-two"
}}));
await new Promise((resolve) => setImmediate(resolve));
assert.equal(pendingHistory.length, 4, "409 automatically restarts at page one");
assert.equal(pendingHistory[3].cursor, null);
pendingHistory[3].resolve({state: "ready", page: {epoch: "race-two", complete: true, rows: [{work_id: "task_after_restart"}]}});
await new Promise((resolve) => setImmediate(resolve));
assert.ok(raceContainer.textContent.includes("epoch_changed"), "409 restart reason must remain visible");
assert.ok(raceContainer.textContent.includes("task_after_restart"));
assert.ok(!raceContainer.textContent.includes("task_new"), "pre-restart pages must be cleared");
