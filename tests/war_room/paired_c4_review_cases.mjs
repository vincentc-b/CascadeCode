import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createElement } from "./plan_dom_fixture.mjs";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const { createPairedNavigation, initPairedC4Review } = require(
  join(repoRoot, "cascade/war_room/static/plan_viewer.js")
);

function target(kind, semanticId, drillViewKey, drillLevel) {
  return {
    kind,
    semantic_id: semanticId,
    drill_view_key: drillViewKey,
    drill_level: drillLevel,
  };
}

function side(repository, revision, targets) {
  return { repository_key: repository, revision, svg: "<svg/>", targets };
}

const payload = {
  state: "ready",
  summary: "2 affected views",
  changed_views: [
    ["context", "systemContextViews"],
    ["payments", "containerViews"],
  ],
  views: [
    {
      key: "context",
      level: "systemContextViews",
      state: "changed",
      current: side("docs-a", "a".repeat(40), [
        target("element", "system.shop", "payments", "containerViews"),
        target("relationship", "relationship.checkout"),
      ]),
      proposed: side("docs-b", "b".repeat(40), [
        target("element", "system.shop", "payments", "containerViews"),
        target("relationship", "relationship.checkout"),
        target("relationship", "relationship.new"),
      ]),
    },
    {
      key: "payments",
      level: "containerViews",
      state: "added",
      current: null,
      proposed: side("docs-b", "b".repeat(40), [target("element", "container.api")]),
    },
  ],
  legend: [],
  requirements: ["REQ-7"],
  decisions: ["ADR-4"],
  diffs: { source: "git:model-a..model-b", plan: "git:plan-a..plan-b" },
};

const navigation = createPairedNavigation(payload);
assert.equal(navigation.state.view_key, "context", "first changed view is selected");
assert.equal(navigation.state.level, "systemContextViews");

let result = navigation.select("element", "system.shop", "current");
assert.equal(result.ok, true);
assert.equal(result.resolutions.current.state, "present");
assert.equal(result.resolutions.proposed.state, "present");
assert.equal(navigation.state.selection.source_side, "current");

result = navigation.back();
assert.equal(result.ok, true);
assert.equal(navigation.state.selection, null, "back restores the shared selection state");

result = navigation.select("relationship", "relationship.new", "proposed");
assert.equal(result.ok, true);
assert.equal(result.resolutions.current.state, "absent");
assert.equal(result.resolutions.proposed.state, "present");
assert.equal(
  navigation.select("relationship", "relationship.new", "current").ok,
  false,
  "an absent counterpart cannot become a guessed source selection"
);

result = navigation.showView("payments", "containerViews");
assert.equal(result.ok, true);
assert.equal(navigation.state.selection, null);
assert.equal(navigation.currentView().state, "added");
assert.equal(navigation.back().ok, true);
assert.equal(navigation.state.selection.semantic_id, "relationship.new");

navigation.back();
result = navigation.drill("current", "element", "system.shop");
assert.equal(result.ok, true, "verified drill metadata moves both sides together");
assert.equal(navigation.state.view_key, "payments");
assert.equal(navigation.currentView().current, null, "drill retains an explicit absent side");

const document = { createElement };
function descendants(root) {
  const rows = [];
  function visit(node) {
    rows.push(node);
    for (const child of node.children || []) visit(child);
  }
  visit(root);
  return rows;
}

const errorHost = createElement("section");
initPairedC4Review({
  state: "error",
  summary: "render failed",
  error: "ambiguous semantic binding",
  views: [],
  changed_views: [],
  diffs: { source: "git:model-a..model-b" },
}, { document, host: errorHost });
assert.ok(descendants(errorHost).some((node) => node.textContent === "ambiguous semantic binding"));
assert.ok(descendants(errorHost).some((node) => node.textContent === "git:model-a..model-b"));

const emptyHost = createElement("section");
initPairedC4Review({
  state: "empty",
  summary: "first proposal",
  views: [],
  changed_views: [],
  diffs: {},
}, { document, host: emptyHost });
assert.ok(descendants(emptyHost).some((node) => /No paired diagram views/.test(node.textContent)));

