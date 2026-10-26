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
  assert.ok(first >= 0 && last > first, `missing section: ${start}`);
  return source.slice(first, last);
}

function element(tagName) {
  return {
    tagName,
    textContent: "",
    href: "",
    children: [],
    dataset: {},
    classList: { values: new Set(), add(value) { this.values.add(value); }, contains(value) { return this.values.has(value); } },
    appendChild(child) { this.children.push(child); return child; },
    addEventListener() {},
    setAttribute() {},
  };
}

function allNodes(rootNode) {
  return [rootNode, ...rootNode.children.flatMap(allNodes)];
}

let forgeReviews = {};
const context = {
  document: { createElement: element },
  apiGet: async () => ({ reviews: forgeReviews }),
  boardFocus: null,
  BoardFocusApi: null,
  lastBoardView: null,
  BranchSyncUiApi: null,
  EpicPlanReadinessUi: null,
  OPEN_STATUSES: { backlog: true },
  branchSyncHelpers: () => null,
  actionButton(label, _handler, disabledReason) {
    const button = element("button");
    button.textContent = label;
    button.disabled = !!disabledReason;
    return button;
  },
  actionLink(label, href) {
    const link = element("a");
    link.textContent = label;
    link.href = href;
    return link;
  },
};

const ui = vm.runInNewContext(`
  ${section("  let pendingBriefCancels =", "  function setBriefInventoryRetryVisible(")}
  ${section("  function buildRow(", "  function taskExecutionStatus(")}
  ({ refreshPendingBriefCancels, buildRow });
`, context);
const epic = { id: "epic_025", title: "Flex mode revival", tier: "epic", status: "backlog" };
const reviewUrl = "https://github.com/example/repo/pull/84";

forgeReviews = { epic_025: { url: reviewUrl, number: "84" } };
await ui.refreshPendingBriefCancels(true);
let row = ui.buildRow(epic, "epics", "1_backlog");
let nodes = allNodes(row);
assert(row.classList.contains("board-row-cancelling"));
assert(nodes.some((node) => node.textContent === "Cancelling · awaiting approval"));
assert(nodes.some((node) => node.tagName === "a" && node.href === reviewUrl));
assert(!nodes.some((node) => node.tagName === "button" && node.textContent === "Cancel"));

forgeReviews = {};
await ui.refreshPendingBriefCancels(true);
row = ui.buildRow(epic, "epics", "1_backlog");
nodes = allNodes(row);
assert(!row.classList.contains("board-row-cancelling"));
assert(!nodes.some((node) => node.tagName === "a" && node.href === reviewUrl));
assert(nodes.some((node) => node.tagName === "button" && node.textContent === "Cancel" && !node.disabled));
