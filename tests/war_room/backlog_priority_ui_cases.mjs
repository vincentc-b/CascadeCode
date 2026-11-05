import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const PriorityUi = require(join(repoRoot, "cascade/war_room/static/backlog_priority_ui.js"));

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

function element(tag) {
  const listeners = Object.create(null);
  const classes = new Set();
  return {
    tagName: tag.toUpperCase(),
    dataset: {},
    children: [],
    parentNode: null,
    disabled: false,
    focused: false,
    classList: {
      add(name) { classes.add(name); },
      remove(name) { classes.delete(name); },
      contains(name) { return classes.has(name); },
    },
    setAttribute(name, value) { this[name] = value; },
    appendChild(child) { child.parentNode = this; this.children.push(child); return child; },
    insertBefore(child, sibling) {
      child.parentNode = this;
      const index = this.children.indexOf(sibling);
      this.children.splice(index < 0 ? this.children.length : index, 0, child);
      return child;
    },
    get firstChild() { return this.children[0] || null; },
    addEventListener(name, handler) { (listeners[name] || (listeners[name] = [])).push(handler); },
    dispatch(name, event = {}) {
      event.target = event.target || this;
      event.prevented = false;
      event.stopped = false;
      event.preventDefault = event.preventDefault || function () { this.prevented = true; };
      event.stopPropagation = event.stopPropagation || function () { this.stopped = true; };
      (listeners[name] || []).forEach((handler) => handler(event));
      return event;
    },
    closest(selector) {
      if (selector.includes("button") && this.tagName === "BUTTON") return this;
      if (selector.includes(".board-row-actions") && this.className === "board-row-actions") return this;
      return this.parentNode && this.parentNode.closest ? this.parentNode.closest(selector) : null;
    },
    focus() { this.focused = true; },
    getBoundingClientRect() { return { top: 0, height: 100 }; },
  };
}

function find(node, predicate) {
  if (predicate(node)) return node;
  for (const child of node.children || []) {
    const result = find(child, predicate);
    if (result) return result;
  }
  return null;
}

function createHarness() {
  const requests = [];
  const statuses = [];
  const document = { createElement: element };
  const board = element("section");
  board.querySelector = function (selector) {
    const match = selector.match(/data-id="([^"]+)".*data-backlog-move="([^"]+)"/);
    if (!match) return null;
    const row = find(board, (node) => node.dataset && node.dataset.id === match[1]);
    return row && find(row, (node) => node.dataset && node.dataset.backlogMove === match[2]);
  };
  let view = {
    backlog_feature_priorities: {
      epic_a: { feature_ids: ["feat_1", "feat_2", "feat_3"], token: "token-1" },
      epic_b: { feature_ids: ["feat_b1", "feat_b2"], token: "token-b" },
    },
  };
  const items = [
    { id: "feat_1", parent: "epic_a" },
    { id: "feat_b1", parent: "epic_b" },
    { id: "feat_2", parent: "epic_a" },
    { id: "feat_b2", parent: "epic_b" },
    { id: "feat_3", parent: "epic_a" },
  ];
  let rendered = [];
  const controller = PriorityUi.createController({
    document,
    board,
    apiPost(path, payload) {
      const request = deferred();
      requests.push({ path, payload, request });
      return request.promise;
    },
    setStatus(message, error) { statuses.push({ message, error }); },
    rerender() { render(); },
  });
  function render() {
    controller.syncBoard(view);
    board.children = [];
    const ordered = controller.orderRows(items);
    rendered = ordered.map((item) => item.id);
    ordered.forEach((item) => {
      const row = element("div");
      row.dataset.id = item.id;
      const actions = element("div");
      actions.className = "board-row-actions";
      controller.appendMoveControls(actions, item);
      controller.decorateRow(row, item);
      row.appendChild(actions);
      board.appendChild(row);
    });
    controller.restoreFocus();
  }
  render();
  return {
    board,
    controller,
    requests,
    statuses,
    rendered: () => rendered,
    setView(next) { view = next; },
    render,
    row(id) { return find(board, (node) => node.dataset && node.dataset.id === id); },
    move(id, direction) {
      const row = this.row(id);
      return find(row, (node) => node.dataset && node.dataset.backlogMove === direction);
    },
  };
}

async function settle() {
  await new Promise((resolve) => setImmediate(resolve));
}

// Canonical projection orders each Epic without disturbing inter-Epic slots.
const h = createHarness();
assert.deepEqual(h.rendered(), ["feat_1", "feat_b1", "feat_2", "feat_b2", "feat_3"]);
assert.match(h.row("feat_1").firstChild.textContent, /Drag to reorder/);

// Focused movement is optimistic, submits the full order/token, and restores focus.
const down = h.move("feat_1", "down");
down.dispatch("click");
assert.deepEqual(h.rendered(), ["feat_2", "feat_b1", "feat_1", "feat_b2", "feat_3"]);
assert.deepEqual(h.requests[0].payload, {
  epic_id: "epic_a",
  feature_ids: ["feat_2", "feat_1", "feat_3"],
  expected_token: "token-1",
});
assert.equal(h.move("feat_1", "down").focused, true);
h.requests[0].request.resolve({
  body: { ok: true, epic_id: "epic_a", feature_ids: ["feat_2", "feat_1", "feat_3"], token: "token-2" },
});
await settle();
assert.deepEqual(h.rendered(), ["feat_2", "feat_b1", "feat_1", "feat_b2", "feat_3"]);
assert.equal(h.move("feat_1", "down").focused, true);

// A refreshed server projection remains canonical after success.
h.setView({
  backlog_feature_priorities: {
    epic_a: { feature_ids: ["feat_2", "feat_1", "feat_3"], token: "token-2" },
    epic_b: { feature_ids: ["feat_b1", "feat_b2"], token: "token-b" },
  },
});
h.render();
assert.deepEqual(h.rendered(), ["feat_2", "feat_b1", "feat_1", "feat_b2", "feat_3"]);

// Dragging an action control is refused and cannot start a reorder.
const source = h.row("feat_1");
const action = h.move("feat_1", "up");
const isolated = source.dispatch("dragstart", { target: action });
assert.equal(isolated.prevented, true);
const suppressedClick = source.dispatch("click", { target: action });
assert.equal(suppressedClick.prevented, true);
assert.equal(suppressedClick.stopped, true);
assert.equal(h.requests.length, 1);

// Drag/drop stays within an Epic; a cross-Epic target is ignored.
source.dispatch("dragstart", { dataTransfer: { setData() {} } });
assert.equal(h.controller.isDragging(), true);
const crossEpic = h.row("feat_b1").dispatch("drop", { clientY: 10 });
assert.equal(crossEpic.prevented, false);
assert.equal(h.requests.length, 1);
source.dispatch("dragend");
assert.equal(h.controller.isDragging(), false);

// A same-Epic drop submits a complete optimistic order.
source.dispatch("dragstart", { dataTransfer: { setData() {} } });
h.row("feat_3").dispatch("drop", { clientY: 90 });
assert.deepEqual(h.requests[1].payload.feature_ids, ["feat_2", "feat_3", "feat_1"]);
h.requests[1].request.resolve({
  body: { feature_ids: ["feat_2", "feat_3", "feat_1"], token: "token-3" },
});
await settle();

// Stale failure adopts the server response, restores it visibly, and explains recovery.
const staleMove = h.move("feat_3", "up");
staleMove.dispatch("click");
h.requests[2].request.reject(Object.assign(new Error("stale"), {
  body: {
    code: "stale_priority",
    feature_ids: ["feat_3", "feat_2", "feat_1"],
    token: "token-4",
  },
}));
await settle();
assert.deepEqual(h.rendered(), ["feat_3", "feat_b1", "feat_2", "feat_b2", "feat_1"]);
assert.equal(h.move("feat_3", "down").focused, true);
assert.equal(h.statuses.at(-1).error, true);
assert.match(h.statuses.at(-1).message, /changed elsewhere.*Restored/i);

// The visible Epic backlog uses the same drag and keyboard controls with its own API.
const epicBoard = element("section");
epicBoard.querySelector = function (selector) {
  const match = selector.match(/data-id="([^"]+)".*data-backlog-move="([^"]+)"/);
  if (!match) return null;
  const row = find(epicBoard, (node) => node.dataset && node.dataset.id === match[1]);
  return row && find(row, (node) => node.dataset && node.dataset.backlogMove === match[2]);
};
const epicRequests = [];
const epicItems = ["epic_1", "epic_2", "epic_3"].map((id) => ({ id }));
let epicView = { backlog_epic_priority: {
  epic_ids: ["epic_1", "epic_2", "epic_3"], token: "epic-token-1",
} };
let epicRendered = [];
const epicController = PriorityUi.createController({
  scope: "epic",
  document: { createElement: element },
  board: epicBoard,
  apiPost(path, payload) {
    const request = deferred();
    epicRequests.push({ path, payload, request });
    return request.promise;
  },
  setStatus() {},
  rerender: renderEpics,
});
function renderEpics() {
  epicController.syncBoard(epicView);
  epicBoard.children = [];
  const ordered = epicController.orderRows(epicItems);
  epicRendered = ordered.map((item) => item.id);
  ordered.forEach((item) => {
    const row = element("div");
    row.dataset.id = item.id;
    const actions = element("div");
    epicController.appendMoveControls(actions, item);
    epicController.decorateRow(row, item);
    row.appendChild(actions);
    epicBoard.appendChild(row);
  });
  epicController.restoreFocus();
}
renderEpics();
assert.match(find(epicBoard, (node) => node.dataset.id === "epic_1").firstChild.textContent, /Drag to reorder/);
const epicSource = find(epicBoard, (node) => node.dataset.id === "epic_2");
epicSource.dispatch("dragstart", { dataTransfer: { setData() {} } });
find(epicBoard, (node) => node.dataset.id === "epic_1").dispatch("drop", { clientY: 10 });
assert.deepEqual(epicRendered, ["epic_2", "epic_1", "epic_3"]);
assert.equal(epicRequests[0].path, "/api/reorder_backlog_epics");
assert.deepEqual(epicRequests[0].payload, {
  epic_ids: ["epic_2", "epic_1", "epic_3"], expected_token: "epic-token-1",
});
epicRequests[0].request.resolve({ body: {
  epic_ids: ["epic_2", "epic_1", "epic_3"], token: "epic-token-2",
} });
await settle();
epicView = { backlog_epic_priority: {
  epic_ids: ["epic_2", "epic_1", "epic_3"], token: "epic-token-2",
} };
renderEpics();
const epicMove = find(
  find(epicBoard, (node) => node.dataset.id === "epic_3"),
  (node) => node.dataset.backlogMove === "up",
);
epicMove.dispatch("click");
assert.deepEqual(epicRequests[1].payload.epic_ids, ["epic_2", "epic_3", "epic_1"]);
epicRequests[1].request.resolve({ body: {
  epic_ids: ["epic_2", "epic_3", "epic_1"], token: "epic-token-3",
} });
await settle();

console.log("backlog_priority_ui_cases: ok");
