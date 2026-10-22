import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const {
  defaultBoardFocus,
  toggleCompletedCollapsed,
  countVisibleInColumn,
  applyBoardLens,
  toggleEpicSelection,
} = require(join(repoRoot, "cascade/war_room/static/board_focus.js"));

const defaults = defaultBoardFocus();
assert.equal(defaults.selected_epic_id, null);
assert.equal(defaults.selected_feature_id, null);
assert.equal(defaults.completed_collapsed.epics, true);
assert.equal(defaults.completed_collapsed.features, true);
assert.equal(defaults.completed_collapsed.tasks, true);

let focus = defaults;
assert.equal(focus.completed_collapsed.epics, true);
focus = toggleCompletedCollapsed(focus, "epics");
assert.equal(focus.completed_collapsed.epics, false);
assert.equal(focus.completed_collapsed.features, true);
focus = toggleCompletedCollapsed(focus, "epics");
assert.equal(focus.completed_collapsed.epics, true);

focus = toggleCompletedCollapsed(focus, "features");
assert.equal(focus.completed_collapsed.features, false);
focus = toggleCompletedCollapsed(focus, "tasks");
assert.equal(focus.completed_collapsed.tasks, false);

const view = {
  epics: { "3_completed": [{ id: "e1" }, { id: "e2" }] },
  features: { "3_completed": [] },
  tasks: { "1_backlog": [{ id: "t1" }], "3_completed": [{ id: "t2" }] },
};
assert.equal(countVisibleInColumn(view, "epics", "3_completed"), 2);
assert.equal(countVisibleInColumn(view, "features", "3_completed"), 0);
assert.equal(countVisibleInColumn(view, "tasks", "3_completed"), 1);
assert.equal(countVisibleInColumn(view, "tasks", "1_backlog"), 1);
assert.equal(countVisibleInColumn(null, "epics", "3_completed"), 0);

const lensView = {
  epics: {
    "1_backlog": [],
    "2_active": [
      { id: "epic_a", title: "Active A" },
      { id: "epic_b", title: "Active B" },
    ],
    "3_completed": [],
  },
  features: {
    "1_backlog": [],
    "2_active": [],
    "3_completed": [
      { id: "feat_a_done", parent: "epic_a" },
      { id: "feat_b_done", parent: "epic_b" },
    ],
  },
  tasks: { "1_backlog": [], "2_active": [], "3_completed": [] },
};
assert.equal(countVisibleInColumn(lensView, "features", "3_completed"), 2);
let lensFocus = defaultBoardFocus();
lensFocus = toggleEpicSelection(lensFocus, "epic_a", lensView);
const filteredView = applyBoardLens(lensView, lensFocus);
assert.equal(countVisibleInColumn(filteredView, "features", "3_completed"), 1);
assert.equal(countVisibleInColumn(lensView, "features", "3_completed"), 2);

const boundedEpicsView = {
  epics: {
    "1_backlog": [],
    "2_active": [{ id: "epic_active", title: "Active" }],
    "3_completed": [
      { id: "epic_008", title: "Done 8" },
      { id: "epic_009", title: "Done 9" },
      { id: "epic_010", title: "Done 10" },
    ],
  },
  features: { "1_backlog": [], "2_active": [], "3_completed": [] },
  tasks: { "1_backlog": [], "2_active": [], "3_completed": [] },
};

function completedEpicIds(view) {
  return (view.epics["3_completed"] || []).map(function (row) {
    return row.id;
  });
}

let boundedFocus = defaultBoardFocus();
boundedFocus = toggleEpicSelection(boundedFocus, "epic_active", boundedEpicsView);
const boundedIds = completedEpicIds(boundedEpicsView);
assert.deepEqual(boundedIds, ["epic_008", "epic_009", "epic_010"]);

boundedFocus = toggleCompletedCollapsed(boundedFocus, "epics");
assert.deepEqual(completedEpicIds(boundedEpicsView), boundedIds);
assert.equal(
  countVisibleInColumn(applyBoardLens(boundedEpicsView, boundedFocus), "epics", "3_completed"),
  3
);
assert.equal(boundedFocus.selected_epic_id, "epic_active");

boundedFocus = toggleCompletedCollapsed(boundedFocus, "epics");
assert.deepEqual(completedEpicIds(boundedEpicsView), boundedIds);
assert.equal(
  countVisibleInColumn(applyBoardLens(boundedEpicsView, boundedFocus), "epics", "3_completed"),
  3
);

console.log("board_focus_collapse_cases: ok");
