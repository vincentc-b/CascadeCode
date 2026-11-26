import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const source = readFileSync(join(root, "cascade/war_room/static/war_room.js"), "utf8");

function section(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first);
  assert.ok(first >= 0 && last > first, `missing script section: ${start}`);
  return source.slice(first, last);
}

class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.children = [];
    this._text = "";
    this.attributes = {};
    this.className = "";
    this.disabled = false;
    this.listeners = {};
    this.classList = { add: (...names) => { this.className += " " + names.join(" "); } };
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(""); }
  set innerHTML(_value) { this._text = ""; this.children = []; }
  appendChild(child) { this.children.push(child); return child; }
  prepend(child) { this.children.unshift(child); return child; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, handler) { this.listeners[name] = handler; }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function descendants(element) {
  return element.children.flatMap((child) => [child, ...descendants(child)]);
}

const panel = new Element("section");
const document = { createElement: (tagName) => new Element(tagName) };
const requests = [];
const context = { document, encodeURIComponent, String, Array, Object, console };
context.globalThis = context;
context.panel = panel;
context.apiGetStub = (path) => {
  const call = deferred();
  requests.push({ path, ...call });
  return call.promise;
};

const script = `
  const el = { recoveryCurrentSummary: globalThis.panel };
  let focusGraphId = "epic_001";
  function apiGet(path) { return globalThis.apiGetStub(path); }
  ${section("  function appendRecoveryIncident(", "  function actionButton(")}
  ${section("  let recoveryProgressEpoch = 0;", "  let inflightChatFetch = null;")}
  ({
    renderCurrentRecoveryProgress,
    loadCurrentRecoveryProgress,
    setFocus: (value) => { focusGraphId = value; },
  });
`;
const api = vm.runInNewContext(script, context);

function entry(id, state, target = null) {
  return {
    entry_id: id,
    action_id: `action:${id}`,
    generation: `generation:${id}`,
    state,
    stage: state === "requested_queued" ? "queued" : "investigation",
    owner: "feature_team",
    safe_reason: "<img src=x onerror=alert(1)>",
    occurred_at: null,
    freshness: "fresh",
    attempt_number: 2,
    prerequisite: "review",
    next_step: "inspect safely",
    target,
    receipt_refs: ["receipt-1"],
    milestone_refs: ["message-1"],
  };
}

api.renderCurrentRecoveryProgress({
  work_id: "epic_001",
  revision: "revision-1",
  completeness: "incomplete",
  observed_at: "2026-11-26T04:02:25+00:00",
  expires_at: "2026-11-26T04:02:55+00:00",
  lag: { backlog_count: 1, oldest_pending_at: "2026-11-26T03:58:01+00:00" },
  items: [entry("one", "requested_queued", "javascript:alert(1)"), entry("two", "executing", "/api/doc/task_1")],
  next_cursor: null,
});
assert.match(panel.textContent, /Queued · not executing/);
assert.match(panel.textContent, /Concurrent: Executing/);
assert.match(panel.textContent, /Occurred: time unavailable/);
assert.match(panel.textContent, /delivery lag 1/);
assert.match(panel.textContent, /Committed milestone/);
assert.match(panel.textContent, /<img src=x onerror=alert\(1\)>/, "unsafe text remains inert text");
assert.equal(descendants(panel).some((node) => node.href === "javascript:alert(1)"), false);
assert.equal(descendants(panel).some((node) => node.href === "/api/doc/task_1"), true);

const epicLoad = api.loadCurrentRecoveryProgress("epic_001");
api.setFocus("feat_001");
const featureLoad = api.loadCurrentRecoveryProgress("feat_001");
requests[1].resolve({ work_id: "feat_001", revision: "feature-rev", items: [entry("feature", "investigating")], next_cursor: null });
await featureLoad;
assert.match(panel.textContent, /work feat_001 · projection feature-rev/);
requests[0].resolve({ work_id: "epic_001", revision: "epic-rev", items: [entry("epic", "executing")], next_cursor: null });
await epicLoad;
assert.doesNotMatch(panel.textContent, /projection epic-rev/, "a late prior-graph response is refused");

const first = api.loadCurrentRecoveryProgress("feat_001");
requests[2].resolve({ work_id: "feat_001", revision: "old-rev", items: [entry("old", "investigating")], next_cursor: "cursor-old" });
await first;
const continuation = api.loadCurrentRecoveryProgress("feat_001", "cursor-old", "old-rev");
requests[3].reject({ status: 409, body: { error: { code: "revision_changed" } } });
await new Promise((resolve) => setImmediate(resolve));
requests[4].resolve({ work_id: "feat_001", revision: "new-rev", items: [entry("new", "verification_pending")], next_cursor: null });
await continuation;
assert.match(panel.textContent, /projection new-rev/, "a changed revision restarts instead of splicing pages");
assert.doesNotMatch(panel.textContent, /action:old/);
