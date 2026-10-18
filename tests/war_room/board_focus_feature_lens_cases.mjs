import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const {
  defaultBoardFocus,
  applyEpicLens,
  applyFeatureLens,
  applyBoardLens,
  toggleFeatureSelection,
  applyFeatureSelection,
  isTasksLensEmpty,
  reconcileFocusWithLens,
} = require(join(repoRoot, "cascade/war_room/static/board_focus.js"));

const view = {
  epics: {
    "1_backlog": [],
    "2_active": [{ id: "epic_a", title: "Active A" }],
    "3_completed": [],
  },
  features: {
    "1_backlog": [{ id: "feat_a1", parent: "epic_a", title: "F1" }],
    "2_active": [{ id: "feat_a2", parent: "epic_a", title: "F2" }],
    "3_completed": [],
  },
  tasks: {
    "1_backlog": [
      { id: "task_1", parent: "feat_a1" },
      { id: "task_other", parent: "feat_a2" },
    ],
    "2_active": [{ id: "task_2", parent: "feat_a1" }],
    "3_completed": [{ id: "task_done", parent: "feat_a1" }],
  },
};

let focus = defaultBoardFocus();

// Null feature → no tasks (not all tasks)
assert.equal(isTasksLensEmpty(focus), true);
const noFeatureLens = applyFeatureLens(view, focus);
assert.deepEqual(noFeatureLens.tasks["1_backlog"], []);
assert.deepEqual(noFeatureLens.tasks["2_active"], []);
assert.deepEqual(noFeatureLens.tasks["3_completed"], []);

// Epic lens still passes tasks through; feature lens filters
const afterEpic = applyEpicLens(view, focus);
assert.deepEqual(afterEpic.tasks, view.tasks);
const boardDefault = applyBoardLens(view, focus);
assert.deepEqual(boardDefault.tasks["1_backlog"], []);

// Selecting a feature sets epic to parent and shows matching tasks
focus = toggleFeatureSelection(focus, "feat_a1", view);
assert.equal(focus.selected_feature_id, "feat_a1");
assert.equal(focus.selected_epic_id, "epic_a");
const featLens = applyBoardLens(view, focus);
assert.deepEqual(featLens.tasks["1_backlog"].map((t) => t.id), ["task_1"]);
assert.deepEqual(featLens.tasks["2_active"].map((t) => t.id), ["task_2"]);
assert.deepEqual(featLens.tasks["3_completed"].map((t) => t.id), ["task_done"]);
assert.equal(featLens.tasks["1_backlog"].some((t) => t.id === "task_other"), false);

// Deselect feature clears feature id only; epic id stays
focus = toggleFeatureSelection(focus, "feat_a1", view);
assert.equal(focus.selected_feature_id, null);
assert.equal(focus.selected_epic_id, "epic_a");
assert.equal(isTasksLensEmpty(focus), true);

// applyFeatureSelection matches feature click
focus = defaultBoardFocus();
const featItem = view.features["2_active"][0];
focus = applyFeatureSelection(focus, featItem);
assert.equal(focus.selected_feature_id, "feat_a2");
assert.equal(focus.selected_epic_id, "epic_a");
const feat2Lens = applyFeatureLens(view, focus);
assert.deepEqual(feat2Lens.tasks["1_backlog"].map((t) => t.id), ["task_other"]);

// Dangling feature: selected but parent not in epic lens (no active epics)
const noActiveView = {
  epics: { "1_backlog": [], "2_active": [], "3_completed": [{ id: "epic_a" }] },
  features: {
    "1_backlog": [{ id: "feat_a1", parent: "epic_a" }],
    "2_active": [],
    "3_completed": [],
  },
  tasks: {
    "1_backlog": [{ id: "task_1", parent: "feat_a1" }],
    "2_active": [],
    "3_completed": [],
  },
};
focus = defaultBoardFocus();
focus.selected_feature_id = "feat_a1";
focus.selected_epic_id = null;
const danglingLens = applyBoardLens(noActiveView, focus);
assert.deepEqual(danglingLens.tasks["1_backlog"], []);
assert.deepEqual(danglingLens.tasks["2_active"], []);
assert.deepEqual(danglingLens.tasks["3_completed"], []);
const reconciled = reconcileFocusWithLens(noActiveView, focus);
assert.equal(reconciled.selected_feature_id, null);
assert.equal(reconciled.selected_epic_id, null);

console.log("board_focus_feature_lens_cases: ok");
