import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createElement } from "./plan_dom_fixture.mjs";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const {
  createPairedNavigation,
  parentViews,
  createSemanticThreadModel,
  initPairedC4Review: initReview,
  renderUnifiedDiff,
  sortedDrillChoices,
} = require(
  join(repoRoot, "cascade/war_room/static/plan_viewer.js")
);

// Semantic projections and a derived comparison SVG are supplied by the server.
function withCombined(payload) {
  return {...payload, views: (payload.views || []).map(view => {
    if (view.combined) return view;
    const before = view.current?.targets || [], after = view.proposed?.targets || [];
    const keys = new Set([...before, ...after].map(t => t.kind + "\0" + t.semantic_id));
    const targets = [...keys].map(key => {
      const old = before.find(t => t.kind + "\0" + t.semantic_id === key);
      const next = after.find(t => t.kind + "\0" + t.semantic_id === key);
      const chosen = next || old;
      return {...chosen, selection_id: chosen.semantic_id, source_side: next ? "proposed" : "current",
        before: old || null, after: next || null};
    });
    const source = view.proposed || view.current;
    return {...view, combined: source && {...source, targets,
      revision: [view.current?.revision, view.proposed?.revision].join(":"),
    }};
  })};
}
function initPairedC4Review(payload, options = {}) {
  const wrapped = {...options};
  for (const key of ["refreshPayload", "loadDraft"]) {
    if (options[key]) wrapped[key] = () => Promise.resolve(options[key]()).then(withCombined);
  }
  return initReview(withCombined(payload), wrapped);
}

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
  ["zeta", "alpha"],
  "drill choices list broader levels before deeper levels"
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
const staleHost = createElement("section");
initPairedC4Review({
  state: "stale_revision",
  owner_work_id: "epic_045",
  approval_context: null,
  summary: "pinned review plan revision is not in the current lineage",
  reason: "pinned review plan revision is not in the current lineage",
  architecture_impact: "no_diagram_change",
  impact_reason: "Existing component boundaries remain accurate.",
  resources: [{
    kind: "design", path: "cascade/war_room/DESIGN.md", revision: "old-revision",
    historical: true, url: "/api/architecture/resources/published/design",
  }],
  views: [], diffs: {},
}, {
  document, host: staleHost,
  loadThreads() { throw new Error("Cannot load threads without a work ID"); },
  loadDocumentationMarkdown() { return "# Published activation design"; },
});
await settle();
assert.ok(descendants(staleHost).some((node) =>
  node.textContent === "No C4 diagram changes proposed."));
assert.ok(!descendants(staleHost).some((node) =>
  node.className === "paired-c4-thread-error"));
assert.ok(!descendants(staleHost).some((node) =>
  node.textContent === "Semantic review threads" || node.textContent === "Reviewed diffs"));
assert.equal(descendants(staleHost).filter((node) =>
  node.textContent === "pinned review plan revision is not in the current lineage").length, 0);
assert.ok(descendants(staleHost).some((node) => /Existing component boundaries/.test(node.textContent)));
descendants(staleHost).find((node) => node.textContent === "Read published design").click();
await settle();
assert.ok(descendants(staleHost).some((node) => /Published activation design/.test(node.textContent)));

const documentDiff = renderUnifiedDiff(document,
  "--- design.md\n+++ design.md\n@@ -1,2 +1,2 @@\n-Choose a red button.\n+Choose a green button.\n Unchanged context.\n");
assert.equal(descendants(documentDiff).filter((node) => node.className === "review-diff-added").length, 1);
assert.equal(descendants(documentDiff).filter((node) => node.className === "review-diff-removed").length, 1);
assert.ok(descendants(documentDiff).some((node) => node.className === "review-diff-inline" && node.textContent === "green"));

initPairedC4Review(payload, { document, host: readyHost });
const readyText = descendants(readyHost).map((node) => node.textContent);
assert.ok(readyText.includes("3 affected views"), "proposal summary stays adjacent to the pair");
assert.ok(readyText.includes("current: docs-a @ " + "a".repeat(40)));
assert.ok(readyText.includes("proposed: docs-b @ " + "b".repeat(40)));
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

// Context documents stay lazy, follow the exact side/view/target selection,
// preserve coverage labels, and enter the existing authoritative requirement
// thread composer without inventing a decision anchor.
const contextHost = createElement("section");
const contextDiagram = createElement("section");
contextHost.appendChild(contextDiagram);
const contextCalls = [];
const markdownCalls = [];
const contextPayload = {
  ...payload,
  documentation_context_url: "/api/architecture/reviews/feat_034_004/context",
  provenance: {
    plan: {
      repository_key: "plans",
      revision: "p".repeat(40),
      path: "docs/feature.md",
    },
  },
};
function contextDocument(id, kind, state = "available") {
  return {
    document_id: id,
    kind,
    title: id + " title",
    state,
    reason: state === "available" ? null : state + "_citation",
    source: state === "missing" ? null : {
      repository_key: "plans",
      revision: "p".repeat(40),
      path: "docs/feature.md",
      section: id,
    },
    provenance: [{ relation: "reviewed_association", evidence_id: "review-exact" }],
    resources: {
      section_url: "/api/architecture/resources/review-exact/section-" + id,
      current_url: "/api/architecture/resources/review-exact/current-" + id,
      proposed_url: "/api/architecture/resources/review-exact/proposed-" + id,
      diff_url: "/api/architecture/resources/review-exact/diff-" + id,
    },
  };
}
const contextReview = initPairedC4Review(contextPayload, {
  document,
  host: contextDiagram,
  loadDocumentationContext(selection, url) {
    contextCalls.push({ ...selection, url });
    const selectedTarget = selection.kind !== "view";
    return {
      mapping_state: selectedTarget ? "unmapped" : "mapped",
      explicit_target_links: selectedTarget ? [
        contextDocument("REQ-MISSING", "requirement", "missing"),
        contextDocument("DEC-STALE", "decision", "stale"),
      ] : [],
      view_links: [
        contextDocument("REQ-7", "requirement"),
        contextDocument("ADR-4", "decision"),
      ],
      owner_context: [{
        code_directory: "cascade/war_room",
        design_owner_directory: "cascade",
        state: "available",
        document_url: "/api/architecture/resources/review-exact/design",
      }],
      broader_index: selectedTarget ? [] : [{
        code_directory: ".",
        design_owner_directory: ".",
        state: "available",
      }],
    };
  },
  loadDocumentationMarkdown(url) {
    markdownCalls.push(url);
    return "- `REQ-7` — Keep reads pinned.";
  },
});
assert.equal(contextCalls.length, 0, "context metadata is not read during board render");
contextHost.querySelector('[data-review-tab="c4"]').click();
assert.equal(contextDiagram.querySelector(".paired-c4-context"), null, "diagrams have no documentation column");
contextHost.querySelector('[data-review-tab="design"]').click();
contextHost.querySelector(".paired-c4-context-toggle").click();
await settle();
await settle();
assert.equal(contextCalls.length, 1);
assert.deepEqual(
  [contextCalls[0].side, contextCalls[0].view_key, contextCalls[0].kind],
  ["proposed", "context", "view"],
  "the initial panel uses the proposed side and exact reviewed view"
);
assert.match(contextCalls[0].url, /side=proposed.*view=context.*kind=view/);
assert.ok(contextHost.querySelector('[data-document-id="REQ-7"]'));
assert.ok(descendants(contextHost).some((node) =>
  node.textContent === "Owning designs (context, not coverage)"));
assert.ok(descendants(contextHost).some((node) =>
  node.textContent === "Broader context index"));
assert.ok(descendants(contextHost).some((node) =>
  node.textContent === "Open current/proposed diff"));

contextHost.querySelector(".paired-c4-context-preview").click();
await settle();
assert.equal(markdownCalls.length, 1, "source Markdown loads only after explicit preview");

const requirement = contextHost.querySelector('[data-document-id="REQ-7"]');
requirement.querySelector(".paired-c4-comment-target").click();
assert.equal(contextReview.draftState().anchor.kind, "requirement");
assert.equal(contextReview.draftState().anchor.target_key, "REQ-7");
assert.equal(contextReview.draftState().anchor.repository_key, "plans");
assert.equal(contextReview.draftState().anchor.source_path, "docs/feature.md");
assert.equal(contextReview.draftState().anchor.source_section, "REQ-7");
assert.equal(contextReview.draftState().anchor.reviewed_tuple_digest, "tuple-exact");

contextHost.querySelector('[data-review-tab="design"]').click();
contextReview.navigation.select("element", "system.shop", "proposed");
contextReview.render();
await settle();
await settle();
assert.equal(contextCalls.at(-1).kind, "element");
assert.equal(contextCalls.at(-1).target, "system.shop");
assert.ok(descendants(contextHost).some((node) =>
  node.textContent === "Unmapped target: no verified explicit requirement or decision link."));
assert.ok(descendants(contextHost).some((node) => node.textContent === "missing · missing_citation"));
assert.ok(descendants(contextHost).some((node) => node.textContent === "stale · stale_citation"));
assert.equal(
  contextHost.querySelector('[data-document-id="DEC-STALE"]')
    .querySelector(".paired-c4-comment-target"),
  null,
  "decisions remain readable and linkable without a new thread anchor"
);
contextReview.stopRefresh();

console.log("paired_c4_review cases ok");



// Level up uses model links even when there is no navigation history.
const hierarchy = [
  { key: "context", level: "systemContextViews", current: { targets: [
    target("element", "system", "components", "componentViews")
  ] } },
  { key: "containers", level: "containerViews", proposed: { targets: [
    target("element", "container", "components", "componentViews")
  ] } },
  { key: "unrelated", level: "containerViews", proposed: { targets: [] } },
  { key: "components", level: "componentViews" }
];
assert.deepEqual(parentViews(hierarchy, hierarchy[3]).map(v => v.key), ["containers"]);
assert.deepEqual(parentViews(hierarchy, hierarchy[0]), []);
assert.deepEqual(parentViews([hierarchy[0], hierarchy[3]], hierarchy[3]).map(v => v.key), ["context"]);

// Code is a fourth-level destination and reverses to the component that owns it.
const codeHierarchy = [
  {key: "components", level: "componentViews", target_ids: ["team"]},
  {key: "team-code", level: "codeViews", target_ids: ["team.graph"]},
];
const codeTargets = [{
  kind: "element", semantic_id: "team",
  drill_choices: [{view_key: "team-code", level: "codeViews"}],
}];
assert.deepEqual(parentViews(codeHierarchy, codeHierarchy[1], codeTargets).map(v => v.key), ["components"]);

// Full document comparison retains context and always orders current before proposed.
const { renderDocumentComparison } = require(join(repoRoot, "cascade/war_room/static/plan_viewer.js"));
const fullComparison = renderDocumentComparison(document, {
  current: "# Heading\n\nOriginal\n\nUnchanged tail",
  proposed: "# Heading\n\nReplacement\n\nUnchanged tail",
  removed_lines: [3], added_lines: [3],
});
assert.equal(fullComparison.children[0].children[0].textContent, "Current");
assert.equal(fullComparison.children[1].children[0].textContent, "Proposed");
assert.match(fullComparison.children[0].children[1].textContent, /Unchanged tail/);
assert.match(fullComparison.children[1].children[1].textContent, /Replacement/);

// Changes below a module remain discoverable from a shared overview, even when
// the new Code view has no current counterpart and arrives first in the payload.
const hierarchyPair = (targets) => ({ current: side("repo", "old", targets), proposed: side("repo", "new", targets) });
const changePath = {
  changed_views: [["new-code", "codeViews"]],
  views: [
    { key: "new-code", level: "codeViews", state: "added", current: null,
      proposed: side("repo", "new", [target("element", "method")]) },
    { key: "modules", level: "componentViews", state: "unchanged", ...hierarchyPair([
      { ...target("element", "module"), state: "unchanged", drill_choices: [
        { view_key: "new-code", level: "codeViews", scope_id: "module" }
      ] },
      { ...target("element", "unrelated"), state: "unchanged", drill_choices: [
        { view_key: "new-code", level: "codeViews", scope_id: "module" }
      ] },
    ]) },
    { key: "containers", level: "containerViews", state: "unchanged", ...hierarchyPair([
      target("element", "container", "modules", "componentViews")
    ]) },
    { key: "overview", level: "systemContextViews", state: "unchanged", ...hierarchyPair([
      target("element", "system", "containers", "containerViews")
    ]) },
  ],
};
const pathNavigation = createPairedNavigation(changePath);
assert.equal(pathNavigation.state.view_key, "overview");
assert.equal(pathNavigation.currentView().proposed.targets[0].contains_changes, true);
const moduleView = pathNavigation.views.find(v => v.key === "modules");
assert.equal(moduleView.proposed.targets[0].contains_changes, true);
assert.equal(moduleView.proposed.targets[0].state, "unchanged", "descendant cues do not invent a direct semantic edit");
assert.equal(moduleView.proposed.targets[1].contains_changes, false, "scope links cannot color unrelated siblings");
assert.equal(changePath.views[1].proposed.targets[0].contains_changes, undefined, "input evidence stays immutable");
pathNavigation.showView("modules", "componentViews");
pathNavigation.updatePayload(changePath);
assert.equal(pathNavigation.state.view_key, "modules", "polling preserves deliberate drill navigation");
const fromPending = createPairedNavigation({ views: [] });
fromPending.updatePayload(changePath);
assert.equal(fromPending.state.view_key, "overview", "pending preview opens at the overview once ready");
const firstArchitecture = createPairedNavigation({
  changed_views: [["code", "codeViews"], ["context", "systemContextViews"]],
  views: [
    { key: "code", level: "codeViews", state: "added", current: null, proposed: side("repo", "new", []) },
    { key: "context", level: "systemContextViews", state: "added", current: null, proposed: side("repo", "new", []) },
  ],
});
assert.equal(firstArchitecture.state.view_key, "context", "a genuinely new model starts at the highest available level");

// One click uses the complete next-level overview when other choices are subsets.
const { preferredDrillChoice } = require(join(repoRoot, "cascade/war_room/static/plan_viewer.js"));
const serviceChoices = [
  {view_key: 'focused', level: 'componentViews'},
  {view_key: 'overview', level: 'componentViews'},
];
const serviceViews = [
  {key: 'focused', level: 'componentViews', ...hierarchyPair([target('element', 'team')])},
  {key: 'overview', level: 'componentViews', ...hierarchyPair([
    target('element', 'team'), target('element', 'workspace'), target('relationship', 'uses-workspace'),
  ])},
];
assert.equal(preferredDrillChoice(serviceChoices, serviceViews, 'proposed').view_key, 'overview');
assert.equal(preferredDrillChoice(serviceChoices, serviceViews, 'current').view_key, 'overview');
const disjointViews = [serviceViews[0], {...serviceViews[1], ...hierarchyPair([
  target('element', 'workspace'), target('element', 'boss'), target('relationship', 'uses-workspace'),
])}];
assert.equal(preferredDrillChoice(serviceChoices, disjointViews, 'proposed'), null, 'larger disjoint view must not be chosen by count');
assert.equal(preferredDrillChoice(serviceChoices, [serviceViews[0]], 'proposed'), null, 'missing inventory cannot prove an overview');
assert.equal(preferredDrillChoice(serviceChoices, [serviceViews[0], {...serviceViews[0],key:'overview'}], 'proposed'), null, 'equal views are genuinely ambiguous');

// Level up reverses ownership links, not mere appearances in a view.
const { preferredParentView } = require(join(repoRoot, "cascade/war_room/static/plan_viewer.js"));
const scopedCode = {key:'workspace-code',level:'codeViews'};
const scopedLink = {view_key:'workspace-code',level:'codeViews',scope_id:'workspace'};
const scopedParents = [
  {key:'all-components',level:'componentViews',...hierarchyPair([
    {...target('element','workspace'),drill_choices:[scopedLink]}, target('element','team'),
  ])},
  {key:'team-components',level:'componentViews',...hierarchyPair([
    {...target('element','repository'),drill_choices:[scopedLink]},
  ])},
];
assert.deepEqual(parentViews([...scopedParents,scopedCode],scopedCode).map(v=>v.key),['all-components']);
assert.deepEqual(parentViews([
  {key:'all-components',level:'componentViews',target_ids:['workspace']},
  {key:'team-components',level:'componentViews',target_ids:['repository']}, scopedCode,
],scopedCode,[
  {...target('element','workspace'),drill_choices:[scopedLink]},
  {...target('element','repository'),drill_choices:[scopedLink]},
]).map(v=>v.key),['all-components'], 'branch browsing follows the same ownership rule');
assert.equal(preferredParentView(serviceViews,[]).key,'overview','direct entry uses the full parent overview');
assert.equal(preferredParentView(serviceViews,[{view_key:'focused',level:'componentViews'}]).key,'focused','up returns to the actual valid parent visited');
assert.equal(preferredParentView(serviceViews,[{view_key:'elsewhere',level:'containerViews'}]).key,'overview','unrelated history is not a parent');
assert.equal(preferredParentView(disjointViews,[]),null,'genuine ambiguous parents remain explicit choices');
assert.equal(preferredParentView([],[]),null,'root has no parent');

// Background review renders must retain each pinned diagram's viewport.
class ViewportParser {
  parseFromString() {
    const svg = createElement("svg");
    svg.localName = "svg";
    svg.setAttribute("viewBox", "0 0 800 600");
    svg.clientWidth = 800;
    svg.clientHeight = 600;
    svg.closest = () => null;
    return { documentElement: svg, querySelector: () => null };
  }
}
const viewportHost = createElement("section");
let viewportPayload = {
  state: "ready", owner_work_id: "epic_047", semantic_threads: [],
  views: [{ key: "context", level: "systemContextViews", state: "changed",
    current: side("project", "base", []), proposed: side("project", "proposal", []) }],
};
const viewportReview = initPairedC4Review(structuredClone(viewportPayload), {
  document, host: viewportHost, DOMParser: ViewportParser,
  refreshPayload: () => structuredClone(viewportPayload),
});
await settle();
function diagramCard(name) {
  return descendants(viewportHost).find(node => node.getAttribute("data-side") === name);
}
function diagramSvg(name) {
  return descendants(diagramCard(name)).find(node => node.localName === "svg");
}
function viewportControl(name, label) {
  descendants(diagramCard(name)).find(node => node.textContent === label).click();
}
const fittedBox = diagramSvg("combined").getAttribute("viewBox");
viewportControl("combined", "Zoom in");
let currentSvg = diagramSvg("combined");
currentSvg.dispatchEvent({ type: "pointerdown", button: 0, clientX: 10, clientY: 10 });
currentSvg.dispatchEvent({ type: "pointermove", clientX: 90, clientY: 50 });
currentSvg.dispatchEvent({ type: "pointerup" });
const pannedBox = currentSvg.getAttribute("viewBox");
assert.notEqual(pannedBox, fittedBox);
await viewportReview.refresh();
assert.equal(diagramSvg("combined").getAttribute("viewBox"), pannedBox);
// Consecutive renders before SVG installation must not erase saved state.
viewportReview.render();
viewportReview.render();
await settle();
assert.equal(diagramSvg("combined").getAttribute("viewBox"), pannedBox);
viewportControl("combined", "Fit");
await viewportReview.refresh();
assert.equal(diagramSvg("combined").getAttribute("viewBox"), fittedBox);
viewportPayload.views[0].proposed.revision = "new-proposal";
await viewportReview.refresh();
assert.equal(diagramSvg("combined").getAttribute("viewBox"), fittedBox,
  "a different pinned diagram starts fitted instead of inheriting old coordinates");
viewportReview.stopRefresh();


// Landscape is optional, not a parent level or the default entry point.
const optionalLandscape = {
  key: "landscape", level: "systemLandscapeViews", state: "changed",
  ...hierarchyPair([target("element", "system", "overview", "systemContextViews")]),
};
const withLandscape = {...changePath, views: [optionalLandscape, ...changePath.views]};
const contextEntry = createPairedNavigation(withLandscape);
assert.equal(contextEntry.currentView().key, "overview");
assert.deepEqual(parentViews(contextEntry.views, contextEntry.currentView()), []);
assert.equal(contextEntry.showView("landscape", "systemLandscapeViews").ok, true);
contextEntry.updatePayload(withLandscape);
assert.equal(contextEntry.currentView().key, "landscape", "refresh preserves an explicit overview selection");
assert.equal(createPairedNavigation({views: [optionalLandscape]}).currentView().key, "landscape",
  "a landscape-only model remains usable");
assert.equal(createPairedNavigation({views: [optionalLandscape, changePath.views[2]]}).currentView().key,
  "containers", "missing context falls back to an available detail view");
