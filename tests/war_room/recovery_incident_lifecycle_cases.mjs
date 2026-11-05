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
    this.className = "";
    this.textContent = "";
    this.attributes = {};
    this.classList = { add: (...names) => { this.className += " " + names.join(" "); } };
  }
  appendChild(child) { this.children.push(child); return child; }
  prepend(child) { this.children.unshift(child); return child; }
  setAttribute(name, value) { this.attributes[name] = value; }
}

function makeClient(storage) {
  const toastList = new Element("ol");
  const context = {
    document: { createElement: (tagName) => new Element(tagName) },
    JSON,
    Object,
    String,
    Array,
    globalThis: { sessionStorage: storage },
  };
  const script = `
    const RECOVERY_TOASTS_STORAGE_KEY = "cascade-war-room-recovery-transitions";
    const el = { toastList: globalThis.toastList };
    let recoveryIncidentTransitions = readRecoveryIncidentTransitions();
    function actionLink(label, href) { const link = document.createElement("a"); link.textContent = label; link.href = href; return link; }
    ${section("  function appendRecoveryIncident(", "  function actionButton(")}
    ({ appendRecoveryIncident, reconcileRecoveryIncidentToasts, transitions: () => recoveryIncidentTransitions });
  `;
  context.globalThis.toastList = toastList;
  return { api: vm.runInNewContext(script, context), toastList };
}

function view(state) {
  const incident = state && {
    state,
    reason: "Merge failed because the target changed.",
    owner: { kind: "epic_team", work_id: "epic_001" },
    affected: { branch: "feat/feat_001", paths: ["cascade/merge.py"] },
    last_attempt: { number: 3, at: "2026-11-03T12:04:00+00:00" },
    next_step: "Approve the recovery review before retrying.",
    target: { kind: "review", href: "https://reviews.example/123" },
  };
  return { epics: {}, tasks: {}, features: { "2_active": [{ id: "feat_001", recovery_incident: incident }] } };
}

const storage = new Map();
storage.getItem = (key) => storage.get(key) || null;
storage.setItem = (key, value) => storage.set(key, value);
const { api, toastList } = makeClient(storage);

const row = new Element("div");
const actions = new Element("div");
api.appendRecoveryIncident(row, actions, view("blocked").features["2_active"][0].recovery_incident);
assert.equal(row.children.length, 1, "one warning surface is rendered on the affected row");
assert.match(row.children[0].children.map((child) => child.textContent).join("\n"), /Reason: Merge failed/);
assert.match(row.children[0].children.map((child) => child.textContent).join("\n"), /Owner: epic_team: epic_001/);
assert.match(row.children[0].children.map((child) => child.textContent).join("\n"), /Affected: branch feat\/feat_001 · paths cascade\/merge.py/);
assert.match(row.children[0].children.map((child) => child.textContent).join("\n"), /Last attempt: #3 at 2026-11-03T12:04:00/);
assert.equal(actions.children[0].textContent, "Open recovery review");

api.reconcileRecoveryIncidentToasts(view("failed"));
api.reconcileRecoveryIncidentToasts(view("failed"));
assert.equal(toastList.children.length, 1, "repeated refreshes do not duplicate a warning toast");
api.reconcileRecoveryIncidentToasts(view("investigating"));
assert.equal(toastList.children.length, 2, "each real state transition is announced once");

const restarted = makeClient(storage);
restarted.api.reconcileRecoveryIncidentToasts(view("investigating"));
assert.equal(restarted.toastList.children.length, 0, "a restart reuses the persisted toast transition");
restarted.api.reconcileRecoveryIncidentToasts(view(null));
assert.deepEqual(restarted.api.transitions(), {}, "resolution clears the active warning transition");
