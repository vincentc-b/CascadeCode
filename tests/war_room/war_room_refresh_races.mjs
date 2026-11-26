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

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

async function waitFor(predicate) {
  for (let attempt = 0; attempt < 20; attempt += 1) {
    if (predicate()) return;
    await new Promise((resolve) => setImmediate(resolve));
  }
  assert.fail("expected asynchronous request was not started");
}

async function testStaleChatReplyCannotReplaceCurrentRoom() {
  const requests = new Map();
  const rendered = [];
  const errors = [];
  const context = {
    apiGet(path) {
      const request = deferred();
      requests.set(path, request);
      return request.promise;
    },
    renderChatMessages(messages) { rendered.push(messages[0].body); },
    updateTranscriptControls() {},
    setTranscriptStatus() {},
    clearChatPollDiagnostic() {},
    reportChatLoadFailure(error) { errors.push(error.message); },
  };
  const script = `
    let focusGraphId = "epic_001";
    let lastChatSnapshot = "";
    let lastChatSnapshotGraphId = null;
    let transcriptEpoch = 0;
    let transcriptState = null;
    const el = { transcriptLoadOlder: null };
    ${section("  function transcriptPagePath", "  function renderCurrentDependencySummary")}
    ({ loadTranscriptLatest, setFocus(id) { focusGraphId = id; } });
  `;
  const chat = vm.runInNewContext(script, context);

  const oldLoad = chat.loadTranscriptLatest("epic_001");
  chat.setFocus("epic_002");
  const currentLoad = chat.loadTranscriptLatest("epic_002");
  requests.get("/api/transcript/v1/epic_002?limit=50").resolve({
    graph_id: "epic_002", incarnation: "current", items: [{id: "2", body: "current room"}],
    high_water_mark: 1, completeness: "complete", older_cursor: null, after_cursor: "after-2"
  });
  await currentLoad;
  requests.get("/api/transcript/v1/epic_001?limit=50").resolve({
    graph_id: "epic_001", incarnation: "old", items: [{id: "1", body: "old room"}],
    high_water_mark: 1, completeness: "complete", older_cursor: null, after_cursor: "after-1"
  });
  await oldLoad;
  assert.deepEqual(rendered, ["current room"]);

  chat.setFocus("epic_001");
  const staleFailure = chat.loadTranscriptLatest("epic_001");
  chat.setFocus("epic_002");
  requests.get("/api/transcript/v1/epic_001?limit=50").reject(new Error("old room failed"));
  await staleFailure;
  assert.deepEqual(errors, []);
}

async function testActionRefreshFetchesAfterPendingPoll() {
  const requests = [];
  const rendered = [];
  const context = {
    apiGet(path) {
      assert.match(path, /^\/api\/board\?_=/);
      const request = deferred();
      requests.push(request);
      return request.promise;
    },
    renderBoard(view) { rendered.push(view.version); },
    refreshPendingBriefCancels() { return Promise.resolve(); },
    refreshFlightReport() { return Promise.resolve(); },
    refreshBossView() { return Promise.resolve(); },
    reportBoardLoadFailure(error) { throw error; },
    document: { hidden: false },
  };
  const script = `
    ${section("  let boardPointerDown = false;", "  function epicIdForFlightLens()")}
    ({ pollBoard, refreshBoard });
  `;
  const board = vm.runInNewContext(script, context);

  const poll = board.pollBoard();
  const actionRefresh = board.refreshBoard();
  assert.equal(requests.length, 1, "poll and action initially share one request");
  requests[0].resolve({ version: "before action" });
  await poll;
  await waitFor(() => requests.length === 2);
  requests[1].resolve({ version: "after action" });
  assert.equal(await actionRefresh, true);
  assert.deepEqual(rendered, ["before action", "after action"]);
}

await testStaleChatReplyCannotReplaceCurrentRoom();
await testActionRefreshFetchesAfterPendingPoll();

async function testHistoricalPollRefreshesProgressWithoutDuplicateReads() {
  const transcriptRequest = deferred();
  const progressRequest = deferred();
  const progressGraphs = [];
  const rendered = [];
  const context = {
    el: { recoveryCurrentSummary: {} },
    loadCurrentRecoveryProgress(graphId, _cursor, _revision, options) {
      progressGraphs.push({ graphId, options });
      return progressRequest.promise;
    },
    transcriptPagePath(graphId, direction, cursor) {
      return `/transcript/${graphId}/${direction}/${cursor}`;
    },
    apiGet(path) {
      assert.equal(path, "/transcript/epic_001/after/after-1");
      return transcriptRequest.promise;
    },
    acceptTranscriptPage(page, graphId, incarnation) {
      return page.graph_id === graphId && page.incarnation === incarnation;
    },
    renderChatMessages(messages) { rendered.push(messages.map((item) => item.id)); },
    updateTranscriptControls() {},
    clearChatPollDiagnostic() {},
    reportChatLoadFailure(error) { throw error; },
  };
  const poller = vm.runInNewContext(`
    let focusGraphId = "epic_001";
    let transcriptEpoch = 1;
    let transcriptState = {
      graphId: "epic_001", incarnation: "incarnation-1", afterCursor: "after-1",
      highWaterMark: 1, completeness: "complete", messages: [{id: "old"}]
    };
    ${section("  let chatPollInFlight = false;", "  async function waitForChatReplies")}
    ({ pollChatSidecar });
  `, context);

  const first = poller.pollChatSidecar();
  const duplicate = poller.pollChatSidecar();
  assert.equal(progressGraphs.length, 1, "one bounded progress GET is shared per poll window");
  assert.equal(progressGraphs[0].graphId, "epic_001");
  assert.equal(progressGraphs[0].options.background, true);
  transcriptRequest.resolve({
    graph_id: "epic_001", incarnation: "incarnation-1", items: [{id: "milestone-2"}],
    after_cursor: "after-2", high_water_mark: 2, completeness: "complete"
  });
  progressRequest.resolve({ work_id: "epic_001", revision: "progress-2" });
  await Promise.all([first, duplicate]);
  assert.equal(JSON.stringify(rendered), JSON.stringify([["old", "milestone-2"]]));
}

await testHistoricalPollRefreshesProgressWithoutDuplicateReads();

async function testBoardAndCancellationLookupRunInParallel() {
  const boardRequest = deferred();
  const cancellationRequest = deferred();
  const rendered = [];
  let cancellationStarted = false;
  const context = {
    apiGet() { return boardRequest.promise; },
    refreshPendingBriefCancels() { cancellationStarted = true; return cancellationRequest.promise; },
    renderBoard(view) { rendered.push(view); },
    refreshFlightReport() { return Promise.resolve(); },
    refreshBossView() { return Promise.resolve(); },
    reportBoardLoadFailure(error) { throw error; },
    document: { hidden: false },
  };
  const board = vm.runInNewContext(`
    ${section("  let boardPointerDown = false;", "  function epicIdForFlightLens()")}
    ({ pollBoard });
  `, context);
  const pending = board.pollBoard();
  assert.ok(cancellationStarted, "cancellation lookup must start before board response");
  boardRequest.resolve({ version: 1 });
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(rendered.length, 0, "retain cancellation safety before enabling board actions");
  cancellationRequest.resolve();
  await pending;
  assert.equal(rendered.length, 1);
}

async function testSlowOptionalPanelsDoNotBlockStartupPolling() {
  const slow = deferred();
  const calls = [];
  const context = {
    wireCompletedCollapseControls() {}, updateFocusUi() {},
    refreshBoard(options) { assert.equal(options.refreshRelated, false); calls.push('board'); return Promise.resolve(); },
    refreshRelatedPanels() { calls.push('related'); return slow.promise; },
    loadChat() { return slow.promise; }, reportChatLoadFailure() {},
    refreshAmendments() { return slow.promise; }, refreshProviders() { return slow.promise; },
    refreshOpenReviews() { return slow.promise; }, pollToasts() { return slow.promise; },
    pollSupervisorHealth() { return slow.promise; }, pollAuditStatus() { return slow.promise; },
    document: { hidden: false, addEventListener() {} }, handleVisibilityChange() {},
    scheduleBoardPoll() { calls.push('polling'); }, boardPollDelayMs: 3000,
    setInterval() { calls.push('interval'); }, pollChatSidecar() {},
  };
  const bootstrap = vm.runInNewContext(`
    ${section("  async function bootstrapWarRoom()", "  bootstrapWarRoom().catch")}
    bootstrapWarRoom;
  `, context);
  await bootstrap();
  assert.ok(calls.includes('related'));
  assert.ok(calls.includes('polling'), 'board polling starts despite pending optional panels');
  assert.equal(calls.filter(c => c === 'interval').length, 4);
  slow.resolve();
}

await testBoardAndCancellationLookupRunInParallel();
await testSlowOptionalPanelsDoNotBlockStartupPolling();

async function testAuditRefreshIsVisibleAndSingleFlight() {
  const requests = [];
  const rendered = [];
  const context = {
    el: {auditStatus: {}},
    AuditStatusUi: {render(_element, payload, options) { rendered.push({payload, options}); }},
    document: {hidden: false},
    URLSearchParams,
    apiGet(path) {
      const request = deferred();
      requests.push({path, request});
      return request.promise;
    },
  };
  const audit = vm.runInNewContext(`
    ${section("  const auditUiState = {};", "  async function apiGet(path)")}
    ({ pollAuditStatus, auditPagePath });
  `, context);

  const first = audit.pollAuditStatus();
  const duplicate = audit.pollAuditStatus();
  assert.equal(requests.length, 1, "five-second refreshes share one status GET");
  assert.equal(requests[0].path, "/api/health/audit");
  requests[0].request.resolve({snapshot: {state: "ready", epoch: "one"}});
  await Promise.all([first, duplicate]);
  assert.equal(rendered.length, 1);

  context.document.hidden = true;
  await audit.pollAuditStatus();
  assert.equal(requests.length, 1, "hidden tabs do not poll audit status");
  context.document.hidden = false;
  const next = audit.pollAuditStatus();
  assert.equal(requests.length, 2);
  requests[1].request.resolve({snapshot: {state: "ready", epoch: "two"}});
  await next;
  const third = audit.pollAuditStatus();
  assert.equal(requests.length, 3);
  requests[2].request.resolve({snapshot: {state: "ready", epoch: "three"}});
  await third;
  assert.deepEqual(
    requests.map(({path}) => path),
    ["/api/health/audit", "/api/health/audit", "/api/health/audit"],
    "browser refreshes remain read-only status requests and never repeat repair admission"
  );
  assert.equal(rendered.length, 3);

  assert.equal(
    audit.auditPagePath("history", "opaque cursor", {
      work_id: "task_044", owner: "feature owner", status: "unverifiable",
      from: "2026-11-14T10:00", to: "2026-11-14T11:00"
    }),
    "/api/health/audit/history?limit=50&cursor=opaque+cursor&work_id=task_044&owner=feature+owner&status=unverifiable&from=2026-11-14T10%3A00Z&to=2026-11-14T11%3A00Z"
  );
}

await testAuditRefreshIsVisibleAndSingleFlight();

async function testBoardPointerGestureSurvivesPoll() {
  const rendered = [];
  const board = vm.runInNewContext(`
    ${section("  let boardPointerDown = false;", "  function epicIdForFlightLens()")}
    ({ renderLoadedBoard, releaseBoardPointer, pressBoardPointer });
  `, { renderBoard(view) { rendered.push(view); }, setTimeout, clearTimeout });
  board.pressBoardPointer();
  board.renderLoadedBoard("first poll");
  board.renderLoadedBoard("newest poll");
  assert.deepEqual(rendered, [], "the originally pressed button survives until click");
  board.releaseBoardPointer();
  board.renderLoadedBoard("arrived during pointerup");
  assert.deepEqual(rendered, [], "pointerup must not replace the button before click");
  await new Promise(resolve => setTimeout(resolve, 10));
  assert.deepEqual(rendered, ["arrived during pointerup"], "only the latest deferred snapshot is applied");
}

await testBoardPointerGestureSurvivesPoll();

async function testLifecycleActionSurvivesRerenders(path, label, pendingLabel, confirmedLabel, confirmedItem) {
  const requests = [];
  const refreshes = [];
  const statuses = [];
  const item = { id: "epic_001", status: path.endsWith("activate_epic") ? "backlog" : "active", plan_approved: false };
  function button() {
    const attributes = new Map();
    let click;
    return {
      disabled: false, isConnected: true,
      addEventListener(_event, handler) { click = handler; },
      click() { click({stopPropagation() {}}); },
      setAttribute(name, value) { attributes.set(name, value); },
      getAttribute(name) { return attributes.get(name); },
      removeAttribute(name) { attributes.delete(name); },
    };
  }
  let boardItem = item;
  const context = {
    document: { createElement: button },
    findBoardItem() { return boardItem; },
    apiPost(path, payload, timeout) {
      const request = deferred();
      requests.push({path, payload, timeout, request});
      return request.promise;
    },
    refreshBoard(options) {
      assert.equal(options.refreshRelated, false);
      const request = deferred();
      refreshes.push(request);
      return request.promise;
    },
    refreshRelatedPanels() { return new Promise(() => {}); },
    renderBoard() {},
    setStatus(message, error) { statuses.push({message, error}); },
  };
  const ui = vm.runInNewContext(`
    const OPEN_STATUSES = { backlog: true, ready_to_plan: true };
    const LIFECYCLE_ACTION_DEADLINE_MS = 120000;
    let lastInvokedBoardAction = null, dispatchBanner = "", lastBoardView = {};
    ${section("  const lifecycleActions = new Map();", "  function branchSyncHelpers()")}
    ${section("  async function dispatch(path", "  /** Dispatch starts the feature")}
    ({ lifecycleActionButton, reconcileLifecycleActions, pendingCount() { return lifecycleActions.size; } });
  `, context);
  const makeButton = () => ui.lifecycleActionButton(item, path, label, pendingLabel, confirmedLabel);
  const first = makeButton();
  first.click();
  assert.equal(first.disabled, true);
  assert.equal(first.textContent, pendingLabel);
  assert.equal(first.getAttribute("aria-busy"), "true");
  assert.equal(requests.length, 1);
  assert.equal(requests[0].timeout, 120000, "the lifecycle write must not use the 10s read deadline");
  assert.equal(requests[0].path, path);
  assert.equal(requests[0].payload.id, item.id);
  first.isConnected = false;
  const rerendered = makeButton();
  assert.equal(rerendered.disabled, true);
  assert.equal(rerendered.textContent, pendingLabel);
  rerendered.click();
  assert.equal(requests.length, 1, "a poll must not enable a duplicate POST");
  const dispatchPending = path.endsWith("approve_epic_plan");
  requests[0].request.resolve({body: {ok: true, dispatch_pending: dispatchPending}});
  await waitFor(() => refreshes.length === 1);
  assert.equal(rerendered.textContent, confirmedLabel, "show durable acknowledgement before a slow GET completes");
  assert.equal(rerendered.disabled, true);
  assert.equal(!!statuses.at(-1).error, dispatchPending);
  refreshes[0].resolve(false); // transient board GET failure
  await new Promise(resolve => setImmediate(resolve));
  const afterFailedRefresh = makeButton();
  assert.equal(afterFailedRefresh.textContent, confirmedLabel);
  assert.equal(afterFailedRefresh.disabled, true);
  boardItem = {...item, ...confirmedItem};
  ui.reconcileLifecycleActions();
  assert.equal(ui.pendingCount(), 0, "canonical read retires the acknowledgement");

  // An explicit refusal permits a new human attempt, but never retries itself.
  boardItem = item;
  const refused = makeButton();
  refused.click();
  requests[1].request.resolve({body: {ok: false, reason: "bad_state"}});
  await waitFor(() => refreshes.length === 2);
  refreshes[1].resolve(true);
  await waitFor(() => ui.pendingCount() === 0);
  assert.equal(makeButton().disabled, false);
  assert.equal(statuses.at(-1).error, true);
  assert.equal(requests.length, 2);

  // A lost response is not proof of failure or permission to repeat the write.
  makeButton().click();
  requests[2].request.reject(new Error("network disconnected"));
  await waitFor(() => refreshes.length === 3);
  assert.match(statuses.at(-1).message, /outcome not confirmed/);
  assert.equal(makeButton().disabled, true);
  refreshes[2].resolve(true);
  await waitFor(() => ui.pendingCount() === 0);
  assert.equal(requests.length, 3);
}

await testLifecycleActionSurvivesRerenders("/api/activate_epic", "Activate team", "Activating…", "Activated — refreshing…", {status: "active"});
await testLifecycleActionSurvivesRerenders("/api/approve_epic_plan", "Approve plan", "Approving…", "Approved — refreshing…", {plan_approved: true});
