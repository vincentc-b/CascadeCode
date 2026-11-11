import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createElement } from "./plan_dom_fixture.mjs";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const {
  createPairedNavigation,
  createSemanticThreadModel,
  initPairedC4Review,
  sortedDrillChoices,
} = require(
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
  owner_work_id: "feat_034_004",
  review_unit_id: "review-exact",
  reviewed_tuple_digest: "tuple-exact",
  repositories: [
    { side: "current", repository_key: "docs-a", revision: "a".repeat(40) },
    { side: "proposed", repository_key: "docs-b", revision: "b".repeat(40) },
  ],
  summary: "3 affected views",
  changed_views: [
    ["context", "systemContextViews"],
    ["payments", "containerViews"],
    ["legacy", "containerViews"],
  ],
  views: [
    {
      key: "context",
      level: "systemContextViews",
      state: "changed",
      current: side("docs-a", "a".repeat(40), [
        target("element", "system.shop", "payments", "containerViews"),
        target("relationship", "relationship.checkout"),
        { ...target("relationship", "relationship.checkout.primary"), label: "checkout" },
        { ...target("relationship", "relationship.checkout.secondary"), label: "checkout" },
      ]),
      proposed: side("docs-b", "b".repeat(40), [
        target("element", "system.shop", "payments", "containerViews"),
        target("relationship", "relationship.checkout"),
        { ...target("relationship", "relationship.checkout.primary"), label: "checkout" },
        { ...target("relationship", "relationship.checkout.secondary"), label: "checkout" },
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
    {
      key: "legacy",
      level: "containerViews",
      state: "removed",
      current: side("docs-a", "a".repeat(40), [target("element", "container.legacy")]),
      proposed: null,
    },
  ],
  legend: [],
  requirements: ["REQ-7"],
  decisions: ["ADR-4"],
  diffs: {
    source: "git:model-a..model-b",
    model: { state: "changed" },
    plan: "git:plan-a..plan-b",
  },
  semantic_threads: [],
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

result = navigation.select("relationship", "relationship.checkout", "proposed");
assert.equal(result.ok, true, "a proposed-side selection drives the same shared state");
assert.equal(result.resolutions.current.state, "present");
assert.equal(result.resolutions.proposed.state, "present");
assert.equal(navigation.state.selection.source_side, "proposed");
navigation.back();

for (const semanticId of [
  "relationship.checkout.primary",
  "relationship.checkout.secondary",
]) {
  result = navigation.select("relationship", semanticId, "current");
  assert.equal(result.ok, true, "parallel same-label relationships resolve by semantic ID");
  assert.equal(result.resolutions.current.target.semantic_id, semanticId);
  assert.equal(result.resolutions.proposed.target.semantic_id, semanticId);
  navigation.back();
}

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

const choiceTarget = {
  kind: "element",
  semantic_id: "system.multi",
  drill_choices: [
    { view_key: "zeta", level: "containerViews", label: "Zeta" },
    { view_key: "alpha", level: "componentViews", label: "Alpha" },
  ],
};
assert.deepEqual(
  sortedDrillChoices(choiceTarget).map((choice) => choice.view_key),
  ["alpha", "zeta"],
  "drill choices use deterministic level/key order"
);
const choicePayload = {
  ...payload,
  views: [
    {
      ...payload.views[0],
      current: side("docs-a", "a".repeat(40), [choiceTarget]),
      proposed: side("docs-b", "b".repeat(40), [choiceTarget]),
    },
    { key: "zeta", level: "containerViews", state: "unchanged", current: null, proposed: null },
    { key: "alpha", level: "componentViews", state: "unchanged", current: null, proposed: null },
  ],
};
const choiceNavigation = createPairedNavigation(choicePayload);
result = choiceNavigation.drill("current", "element", "system.multi");
assert.equal(result.needs_choice, true, "ambiguous containment never guesses a destination");
assert.equal(result.choices.length, 2);
assert.equal(
  choiceNavigation.drill(
    "current", "element", "system.multi", "alpha", "componentViews"
  ).ok,
  true,
  "an explicit verified drill choice drives shared navigation"
);

const refreshedNavigation = createPairedNavigation(payload);
refreshedNavigation.select("element", "system.shop", "current");
refreshedNavigation.updatePayload({ ...payload, views: payload.views.slice(0, 2) });
assert.equal(refreshedNavigation.state.view_key, "context");
assert.equal(
  refreshedNavigation.state.selection.semantic_id,
  "system.shop",
  "refresh preserves a surviving semantic selection"
);
refreshedNavigation.updatePayload({ ...payload, views: payload.views.slice(1) });
assert.equal(refreshedNavigation.state.view_key, "payments");
assert.equal(refreshedNavigation.state.selection, null, "refresh drops only vanished targets");

const inventoryNavigation = createPairedNavigation(payload);
for (const [viewKey, level] of payload.changed_views) {
  assert.equal(inventoryNavigation.showView(viewKey, level).ok, true);
  assert.equal(inventoryNavigation.currentView().key, viewKey, "every changed view is reachable");
}
assert.equal(inventoryNavigation.currentView().state, "removed");
assert.equal(inventoryNavigation.currentView().proposed, null);

const threadNavigation = createPairedNavigation(payload);
const created = [];
const threadModel = createSemanticThreadModel(payload, threadNavigation, {
  createThread(request) {
    created.push(request);
    return { ok: true, comment_id: "cmt_1" };
  },
});
const requirementAnchor = threadModel.buildAnchor("requirement", "REQ-7", "current");
const viewAnchor = threadModel.buildAnchor(
  "view", "context", "current", "context", "systemContextViews"
);
const elementAnchor = threadModel.buildAnchor("element", "system.shop", "proposed");
const relationshipAnchor = threadModel.buildAnchor(
  "relationship", "relationship.new", "proposed"
);
assert.deepEqual(
  [requirementAnchor.kind, viewAnchor.kind, elementAnchor.kind, relationshipAnchor.kind],
  ["requirement", "view", "element", "relationship"],
  "all semantic anchor kinds are authorable"
);
assert.equal(elementAnchor.repository_key, "docs-b", "the selected side retains its repository");
assert.equal(elementAnchor.revision, "b".repeat(40), "the selected side retains its revision");
assert.equal(viewAnchor.view_key, "context");
assert.equal(viewAnchor.level, "systemContextViews");
assert.equal(relationshipAnchor.view_key, null, "model identities are not inferred from view labels");
await threadModel.create(relationshipAnchor, "check the new edge", true);
assert.equal(created[0].semantic_anchor, relationshipAnchor);
assert.equal(created[0].blocking, true);

const currentThread = threadModel.normalize({
  id: "cmt_1", body: "check", author: "human", state: "open", blocking: true,
  semantic_anchor: relationshipAnchor,
});
assert.equal(currentThread.freshness, "current");
assert.equal(threadModel.navigate(currentThread).ok, true);
assert.equal(threadNavigation.state.view_key, "context");
assert.equal(threadNavigation.state.selection.semantic_id, "relationship.new");

const outdated = threadModel.normalize({
  id: "cmt_2", body: "old", author: "human", state: "open", blocking: true,
  semantic_anchor: { ...elementAnchor, revision: "c".repeat(40) },
});
assert.equal(outdated.freshness, "outdated");
assert.equal(outdated.outdated_reason, "revision_mismatch");
assert.equal(outdated.blocking, true, "freshness does not alter blocking state");
assert.equal(outdated.anchor.original_source_reference, "<svg/>");
assert.equal(outdated.anchor.original_diff_link, "git:model-a..model-b");
assert.equal(threadModel.navigate(outdated).ok, false, "outdated targets retain links but do not guess navigation");

const renamedPayload = {
  ...payload,
  views: payload.views.map((view) => ({
    ...view,
    current: view.current && {
      ...view.current,
      targets: view.current.targets.map((item) =>
        item.semantic_id === "system.shop" ? { ...item, semantic_id: "system.store" } : item
      ),
    },
    proposed: view.proposed && {
      ...view.proposed,
      targets: view.proposed.targets.map((item) =>
        item.semantic_id === "system.shop" ? { ...item, semantic_id: "system.store" } : item
      ),
    },
  })),
  diffs: {
    ...payload.diffs,
    model: { identities: [{
      kind: "element", semantic_id: "system.store", previous_semantic_id: "system.shop",
    }] },
  },
};
const renamedNavigation = createPairedNavigation(renamedPayload);
const renamedModel = createSemanticThreadModel(renamedPayload, renamedNavigation);
const renamedThread = renamedModel.normalize({
  id: "cmt_3", body: "reviewed rename", author: "human", state: "open", blocking: false,
  semantic_anchor: elementAnchor,
});
assert.equal(renamedThread.freshness, "current", "only an explicit reviewed identity mapping retains continuity");
assert.equal(renamedModel.navigate(renamedThread).ok, true);
assert.equal(renamedNavigation.state.selection.semantic_id, "system.store");

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

function settle() {
  return new Promise((resolve) => setImmediate(resolve));
}

const errorHost = createElement("section");
initPairedC4Review({
  state: "error",
  summary: "render failed",
  error: "ambiguous semantic binding",
  views: [],
  changed_views: [],
  diffs: { source: "git:model-a..model-b" },
  semantic_threads: [],
}, { document, host: errorHost });
assert.ok(descendants(errorHost).some((node) => node.textContent === "ambiguous semantic binding"));
assert.ok(descendants(errorHost).some((node) => node.textContent === "git:model-a..model-b"));

for (const [state, expected] of [
  ["first", /No paired diagram views.*first/],
  ["empty", /No paired diagram views.*empty/],
  ["removed", /No paired diagram views.*removed/],
  ["unchanged", /No diagram changes/],
  ["partial_acceptance", /Partial acceptance remains pending.*proposal/],
]) {
  const stateHost = createElement("section");
  initPairedC4Review({
    state,
    summary: state + " proposal",
    views: [],
    changed_views: [],
    diffs: {},
    semantic_threads: [],
  }, { document, host: stateHost });
  assert.ok(descendants(stateHost).some((node) => expected.test(node.textContent)));
}

const readyHost = createElement("section");
initPairedC4Review(payload, { document, host: readyHost });
const readyText = descendants(readyHost).map((node) => node.textContent);
assert.ok(readyText.includes("3 affected views"), "proposal summary stays adjacent to the pair");
assert.ok(readyText.includes("docs-a @ " + "a".repeat(40)));
assert.ok(readyText.includes("docs-b @ " + "b".repeat(40)));
assert.ok(readyText.includes("REQ-7"));
assert.ok(readyText.includes("ADR-4"));
assert.ok(readyText.includes("git:model-a..model-b"));
assert.ok(readyText.some((value) => /\"state\": \"changed\"/.test(value)));
assert.ok(readyText.includes("git:plan-a..plan-b"));
await settle();
assert.ok(
  descendants(readyHost).some((node) => /Interaction unsupported:/.test(node.textContent)),
  "a client-side binding failure is actionable and never replaced with static interaction"
);

// The live discussion reconciles roots and replies without discarding local
// drafts, and all lifecycle writes use the owner-routed HTTP contract.
const liveHost = createElement("section");
const livePayload = { ...payload };
delete livePayload.semantic_threads;
const liveModel = createSemanticThreadModel(livePayload, createPairedNavigation(livePayload));
const liveAnchor = liveModel.buildAnchor("element", "system.shop", "proposed");
let liveRows = [
  {
    id: "semantic-root", body: "check the shop", author: "human", state: "open",
    blocking: true, semantic_anchor: liveAnchor, created: "2026-11-10T00:00:00Z",
  },
  {
    id: "semantic-reply-1", parent: "semantic-root", body: "first reply",
    author: "agent", state: "open", blocking: false,
    created: "2026-11-10T00:01:00Z",
  },
];
let refreshedPayload = livePayload;
const lifecycleCalls = [];
const liveReview = initPairedC4Review(livePayload, {
  document,
  host: liveHost,
  loadThreads() { return liveRows; },
  refreshPayload() { return { ...refreshedPayload }; },
  createThread(request) {
    lifecycleCalls.push(["create", request]);
    return { ok: true, comment_id: "semantic-created" };
  },
  replyThread(request) {
    lifecycleCalls.push(["reply", request]);
    liveRows.push({
      id: "semantic-reply-local", parent: request.parent, body: request.body,
      author: "human", state: "open", blocking: false,
      created: "2026-11-10T00:03:00Z",
    });
    return { ok: true };
  },
  resolveThread(request) {
    lifecycleCalls.push(["resolve", request]);
    liveRows = liveRows.map((row) => ({ ...row, state: "resolved" }));
    return { ok: true };
  },
  reopenThread(request) {
    lifecycleCalls.push(["reopen", request]);
    liveRows = liveRows.map((row) => ({ ...row, state: "open" }));
    return { ok: true };
  },
});
await settle();
assert.equal(liveHost.querySelectorAll(".paired-c4-thread-reply").length, 1);
assert.equal(liveHost.querySelector(".paired-c4-thread-resolve").textContent, "Resolve");

const replyDraft = liveHost.querySelector(".paired-c4-thread-reply-body-input");
replyDraft.value = "preserve this reply";
replyDraft.dispatchEvent({ type: "input" });
liveRows.push({
  id: "semantic-reply-incoming", parent: "semantic-root", body: "incoming reply",
  author: "agent", state: "open", blocking: false,
  created: "2026-11-10T00:02:00Z",
});
await liveReview.refresh();
assert.equal(liveHost.querySelectorAll(".paired-c4-thread-reply").length, 2);
assert.equal(
  liveHost.querySelector(".paired-c4-thread-reply-body-input").value,
  "preserve this reply",
  "incoming refresh preserves the local reply draft"
);
liveHost.querySelector(".paired-c4-thread-reply-form").dispatchEvent({ type: "submit" });
await settle();
assert.equal(lifecycleCalls[0][0], "reply");
assert.equal(lifecycleCalls[0][1].parent, "semantic-root");
assert.equal(lifecycleCalls[0][1].body, "preserve this reply");
assert.equal(liveHost.querySelectorAll(".paired-c4-thread-reply").length, 3);

liveHost.querySelector(".paired-c4-thread-resolve").click();
await settle();
assert.equal(lifecycleCalls[1][0], "resolve");
assert.equal(lifecycleCalls[1][1].doc_id, payload.owner_work_id);
assert.equal(liveHost.querySelector(".paired-c4-thread-reopen").textContent, "Reopen");
liveHost.querySelector(".paired-c4-thread-reopen").click();
await settle();
assert.equal(lifecycleCalls[2][0], "reopen");
assert.ok(liveHost.querySelector(".paired-c4-thread-resolve"));

// A composer opened in an old tab keeps its draft, but tuple replacement
// disables submission until the reviewer explicitly rebinds the same target.
liveHost.querySelector(".paired-c4-comment-target").click();
const rootDraft = liveHost.querySelector(".paired-c4-thread-body");
rootDraft.value = "draft from the old tuple";
rootDraft.dispatchEvent({ type: "input" });
liveReview.navigation.select("element", "system.shop", "proposed");
refreshedPayload = {
  ...livePayload,
  review_unit_id: "review-next",
  reviewed_tuple_digest: "tuple-next",
};
await liveReview.refresh();
assert.equal(liveReview.selection().semantic_id, "system.shop");
assert.equal(liveReview.draftState().body, "draft from the old tuple");
assert.equal(liveReview.draftState().needs_review, true);
assert.equal(liveHost.querySelector(".paired-c4-thread-send").disabled, true);
assert.ok(liveHost.querySelector(".paired-c4-thread-review-target"));
liveHost.querySelector(".paired-c4-thread-review-target").click();
assert.equal(liveReview.draftState().needs_review, false);
assert.equal(liveReview.draftState().anchor.reviewed_tuple_digest, "tuple-next");
liveHost.querySelector(".paired-c4-thread-compose").dispatchEvent({ type: "submit" });
await settle();
assert.equal(lifecycleCalls[3][0], "create");
assert.equal(lifecycleCalls[3][1].body, "draft from the old tuple");
assert.equal(lifecycleCalls[3][1].semantic_anchor.reviewed_tuple_digest, "tuple-next");

liveRows[0] = { ...liveRows[0], state: "open", freshness: "outdated", outdated_reason: "review_tuple_mismatch" };
await liveReview.refresh();
assert.ok(liveHost.querySelector(".paired-c4-thread-outdated-blocking"));
liveReview.stopRefresh();

const grouped = createSemanticThreadModel(livePayload, createPairedNavigation(livePayload), {
  loadThreads() { return liveRows; },
});
await grouped.load();
assert.equal(grouped.state.threads.length, 1, "Markdown roots are excluded from semantic discussion");
assert.equal(grouped.state.threads[0].replies.length, 3);

console.log("paired_c4_review cases ok");

