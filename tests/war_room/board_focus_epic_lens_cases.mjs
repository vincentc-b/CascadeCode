import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const {
  defaultBoardFocus,
  featureParentIds,
  applyEpicLens,
  toggleEpicSelection,
  isFeaturesLensEmpty,
} = require(join(repoRoot, "cascade/war_room/static/board_focus.js"));

const view = {
  epics: {
    "1_backlog": [{ id: "epic_bl", title: "Backlog epic" }],
    "2_active": [
      { id: "epic_a", title: "Active A" },
      { id: "epic_b", title: "Active B" },
    ],
    "3_completed": [{ id: "epic_done", title: "Done epic" }],
  },
  features: {
    "1_backlog": [
      { id: "feat_a1", parent: "epic_a" },
      { id: "feat_b1", parent: "epic_b" },
      { id: "feat_bl", parent: "epic_bl" },
    ],
    "2_active": [{ id: "feat_a2", parent: "epic_a" }],
    "3_completed": [{ id: "feat_done", parent: "epic_done" }],
  },
  tasks: {
    "1_backlog": [{ id: "task_1", parent: "feat_a1" }],
    "2_active": [],
    "3_completed": [],
  },
};

let focus = defaultBoardFocus();

// Default lens: all epics in 2_active
assert.deepEqual(featureParentIds(view, focus).sort(), ["epic_a", "epic_b"]);
const defaultLens = applyEpicLens(view, focus);
assert.deepEqual(
  defaultLens.features["1_backlog"].map((f) => f.id).sort(),
  ["feat_a1", "feat_b1"]
);
assert.equal(defaultLens.features["1_backlog"].some((f) => f.id === "feat_bl"), false);
assert.equal(defaultLens.features["3_completed"].some((f) => f.id === "feat_done"), false);
assert.deepEqual(defaultLens.tasks, view.tasks);
assert.equal(isFeaturesLensEmpty(view, focus), false);

// Single-epic selection replaces the active set (no union)
focus = toggleEpicSelection(focus, "epic_a", view);
assert.equal(focus.selected_epic_id, "epic_a");
assert.deepEqual(featureParentIds(view, focus), ["epic_a"]);
const singleLens = applyEpicLens(view, focus);
assert.deepEqual(
  singleLens.features["1_backlog"].map((f) => f.id),
  ["feat_a1"]
);
assert.deepEqual(singleLens.features["2_active"].map((f) => f.id), ["feat_a2"]);

// Backlog epic as lens
focus = defaultBoardFocus();
focus = toggleEpicSelection(focus, "epic_bl", view);
assert.deepEqual(featureParentIds(view, focus), ["epic_bl"]);
const backlogLens = applyEpicLens(view, focus);
assert.deepEqual(backlogLens.features["1_backlog"].map((f) => f.id), ["feat_bl"]);

// Completed epic as lens
focus = defaultBoardFocus();
focus = toggleEpicSelection(focus, "epic_done", view);
const doneLens = applyEpicLens(view, focus);
assert.deepEqual(doneLens.features["3_completed"].map((f) => f.id), ["feat_done"]);

// Clear selected_feature_id when parent leaves lens on epic select
focus = defaultBoardFocus();
focus.selected_feature_id = "feat_b1";
focus = toggleEpicSelection(focus, "epic_a", view);
assert.equal(focus.selected_epic_id, "epic_a");
assert.equal(focus.selected_feature_id, null);

// Deselect epic; feature cleared when parent not in default lens
focus = defaultBoardFocus();
focus.selected_epic_id = "epic_done";
focus.selected_feature_id = "feat_done";
focus = toggleEpicSelection(focus, "epic_done", view);
assert.equal(focus.selected_epic_id, null);
assert.equal(focus.selected_feature_id, null);

// Feature kept when still in lens after deselect
focus = defaultBoardFocus();
focus.selected_epic_id = "epic_a";
focus.selected_feature_id = "feat_a1";
focus = toggleEpicSelection(focus, "epic_a", view);
assert.equal(focus.selected_epic_id, null);
assert.equal(focus.selected_feature_id, "feat_a1");

// Empty-state predicate
const emptyView = {
  epics: { "1_backlog": [], "2_active": [], "3_completed": [] },
  features: { "1_backlog": [{ id: "f", parent: "x" }], "2_active": [], "3_completed": [] },
  tasks: { "1_backlog": [], "2_active": [], "3_completed": [] },
};
assert.equal(isFeaturesLensEmpty(emptyView, defaultBoardFocus()), true);
const emptyLens = applyEpicLens(emptyView, defaultBoardFocus());
assert.deepEqual(emptyLens.features["1_backlog"], []);
assert.deepEqual(emptyLens.features["2_active"], []);
assert.deepEqual(emptyLens.features["3_completed"], []);

console.log("board_focus_epic_lens_cases: ok");
