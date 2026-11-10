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
    clearChatPollDiagnostic() {},
    reportChatLoadFailure(error) { errors.push(error.message); },
  };
  const script = `
    let focusGraphId = "epic_001";
    let lastChatSnapshot = "";
    let lastChatSnapshotGraphId = null;
    ${section("  let inflightChatFetch = null;", "  let chatPollInFlight = false;")}
    ({ loadChat, setFocus(id) { focusGraphId = id; } });
  `;
  const chat = vm.runInNewContext(script, context);

  const oldLoad = chat.loadChat();
  chat.setFocus("epic_002");
  const currentLoad = chat.loadChat();
  requests.get("/api/chat/epic_002").resolve([{ body: "current room" }]);
  await currentLoad;
  requests.get("/api/chat/epic_001").resolve([{ body: "old room" }]);
  await oldLoad;
  assert.deepEqual(rendered, ["current room"]);

  chat.setFocus("epic_001");
  const staleFailure = chat.loadChat();
  chat.setFocus("epic_002");
  requests.get("/api/chat/epic_001").reject(new Error("old room failed"));
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
    ${section("  let boardRefreshInFlight = null;", "  function epicIdForFlightLens()")}
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
    ${section("  let boardRefreshInFlight = null;", "  function epicIdForFlightLens()")}
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
