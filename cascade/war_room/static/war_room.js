(function () {
  const app = document.getElementById("war-room-app");
  if (!app) return;

  const defaultEpicId = app.dataset.defaultEpicGraphId || "epic_001";
  let focusGraphId = defaultEpicId;
  let attachedGraphId = null;
  let toastOffset = 0;
  let dispatchBanner = "";

  let amendments = [];
  let selectedAmdId = null;
  let pendingToastFocus = null;
  let amendmentEpicId = defaultEpicId;

  const BoardFocusApi = globalThis.BoardFocus;
  let boardFocus = BoardFocusApi ? BoardFocusApi.defaultBoardFocus() : null;
  let lastBoardView = null;

  const el = {
    board: document.getElementById("war-room-board"),
    bossSummary: document.getElementById("boss-view-summary"),
    chatGraphId: document.getElementById("chat-graph-id"),
    chatMessages: document.getElementById("chat-messages"),
    chatCompose: document.getElementById("chat-compose"),
    chatBody: document.getElementById("chat-body"),
    chatSend: document.getElementById("chat-send"),
    chatStatus: document.getElementById("chat-status"),
    chatPollDebug: document.getElementById("chat-poll-debug"),
    chatPollDebugBody: document.getElementById("chat-poll-debug-body"),
    toastList: document.getElementById("toast-list"),
    attachmentLabel: document.getElementById("attachment-label"),
    btnDetach: document.getElementById("btn-detach"),
    epicChat: document.getElementById("epic-war-room-chat"),
    flightPanel: document.getElementById("flight-report-panel"),
    flightBody: document.getElementById("flight-report-body"),
    featurePlaceholder: document.getElementById("feature-room-placeholder"),
    amendmentPane: document.getElementById("amendment-pane"),
    amendmentPaneStatus: document.getElementById("amendment-pane-status"),
    amendmentList: document.getElementById("amendment-list"),
    amendmentDetail: document.getElementById("amendment-detail"),
    amendmentMeta: document.getElementById("amendment-meta"),
    amendmentReviseNotice: document.getElementById("amendment-revise-notice"),
    diffBefore: document.getElementById("diff-before"),
    diffAfter: document.getElementById("diff-after"),
    amendmentActions: document.getElementById("amendment-actions"),
    rejectForm: document.getElementById("amendment-reject-form"),
    reviseForm: document.getElementById("amendment-revise-form"),
    rejectNote: document.getElementById("reject-note"),
    reviseText: document.getElementById("revise-text"),
    reviseNote: document.getElementById("revise-note"),
    btnAccept: document.getElementById("btn-amd-accept"),
    btnReject: document.getElementById("btn-amd-reject"),
    btnRevise: document.getElementById("btn-amd-revise"),
    providersPane: document.getElementById("providers-pane"),
    providersPaneStatus: document.getElementById("providers-pane-status"),
    providersList: document.getElementById("providers-list"),
    btnCreateBrief: document.getElementById("btn-create-brief"),
    btnPullMain: document.getElementById("btn-pull-main"),
    syncStatus: document.getElementById("sync-status"),
    briefDialog: document.getElementById("brief-dialog"),
    briefForm: document.getElementById("brief-form"),
    briefStatus: document.getElementById("brief-status"),
    briefResult: document.getElementById("brief-result"),
    briefProvider: document.getElementById("brief-provider"),
    briefManagerModel: document.getElementById("brief-manager-model"),
    briefArchitectModel: document.getElementById("brief-architect-model"),
    briefManagerSuggestion: document.getElementById("brief-manager-suggestion"),
    briefArchitectSuggestion: document.getElementById("brief-architect-suggestion"),
    btnCloseBrief: document.getElementById("btn-close-brief"),
    btnCancelBrief: document.getElementById("btn-cancel-brief"),
    btnSubmitBrief: document.getElementById("btn-submit-brief"),
  };

  const AGENT_CHAT_AUTHORS = {
    epic_manager: true,
    epic_architect: true,
    feature_lead: true,
    feature_architect: true,
    boss: true,
  };

  /** Statuses the dispatch law accepts for Activate / Dispatch (cascade/watchdog/dispatch.py _OPEN). */
  const OPEN_STATUSES = { backlog: true, ready_to_plan: true };

  function setStatus(msg, isError) {
    el.chatStatus.textContent = msg || dispatchBanner;
    el.chatStatus.classList.toggle("error", !!isError);
  }

  const LOAD_DEADLINE_MS = 10000;

  function deadlineSignal() {
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
      return AbortSignal.timeout(LOAD_DEADLINE_MS);
    }
    const controller = new AbortController();
    setTimeout(function () {
      controller.abort();
    }, LOAD_DEADLINE_MS);
    return controller.signal;
  }

  function reportBoardLoadFailure(err) {
    const timedOut = err && (err.name === "TimeoutError" || err.name === "AbortError");
    const msg = timedOut ? "Timed out after 10s" : (err && err.message) || "Load failed";
    if (el.board && !el.board.querySelector(".load-deadline")) {
      const note = document.createElement("p");
      note.className = "load-deadline";
      note.textContent = msg;
      el.board.insertBefore(note, el.board.firstChild);
    }
  }

  function reportChatLoadFailure(err, options) {
    const userInitiated = !options || options.userInitiated !== false;
    const timedOut = err && (err.name === "TimeoutError" || err.name === "AbortError");
    const msg = timedOut ? "Timed out after 10s" : (err && err.message) || "Load failed";
    if (userInitiated) {
      setStatus(msg, true);
    }
    noteChatPollDiagnostic(msg, err);
  }

  let lastChatPollDiagnostic = "";
  let lastChatPollDiagnosticAt = 0;

  function noteChatPollDiagnostic(msg, err) {
    const detail = msg + (err && err.status ? " (HTTP " + err.status + ")" : "");
    if (detail === lastChatPollDiagnostic && Date.now() - lastChatPollDiagnosticAt < 30000) {
      return;
    }
    lastChatPollDiagnostic = detail;
    lastChatPollDiagnosticAt = Date.now();
    if (typeof console !== "undefined" && console.warn) {
      console.warn("[war-room chat poll]", detail, err || "");
    }
    if (!el.chatPollDebug || !el.chatPollDebugBody) return;
    el.chatPollDebug.hidden = false;
    el.chatPollDebugBody.textContent =
      new Date().toISOString() +
      " " +
      detail +
      (err && err.body ? "\n" + JSON.stringify(err.body, null, 2) : "");
  }

  function clearChatPollDiagnostic() {
    lastChatPollDiagnostic = "";
    if (el.chatPollDebug) el.chatPollDebug.hidden = true;
    if (el.chatPollDebugBody) el.chatPollDebugBody.textContent = "";
  }

  function reportLoadFailure(err) {
    reportBoardLoadFailure(err);
    reportChatLoadFailure(err);
  }

  async function apiGet(path) {
    const resp = await fetch(path, { signal: deadlineSignal(), cache: "no-store" });
    const text = await resp.text();
    let body;
    try {
      body = JSON.parse(text);
    } catch (_e) {
      body = text;
    }
    if (!resp.ok) {
      const err = new Error(typeof body === "object" && body.error ? body.error : resp.statusText);
      err.status = resp.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  async function apiPost(path, payload) {
    const resp = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: deadlineSignal(),
    });
    const text = await resp.text();
    let body;
    try {
      body = JSON.parse(text);
    } catch (_e) {
      body = { error: text || resp.statusText };
    }
    if (!resp.ok) {
      const err = new Error(body.error || resp.statusText);
      err.status = resp.status;
      err.body = body;
      throw err;
    }
    return { status: resp.status, body };
  }

  async function openBriefDialog() {
    el.briefStatus.textContent = "Loading model suggestions…";
    el.briefResult.hidden = true;
    el.briefDialog.showModal();
    try {
      const template = await apiGet("/api/brief/template");
      el.briefProvider.replaceChildren();
      (template.providers || []).forEach(function (provider) {
        const option = document.createElement("option");
        option.value = provider;
        option.textContent = provider;
        option.selected = provider === template.provider;
        el.briefProvider.appendChild(option);
      });
      el.briefManagerModel.value = template.manager_model || "";
      el.briefArchitectModel.value = template.architect_model || "";
      el.briefProvider.onchange = function () {
        const defaults = (template.provider_models || {})[el.briefProvider.value] || {};
        el.briefManagerModel.value = defaults.manager_model || "";
        el.briefArchitectModel.value = defaults.architect_model || "";
      };
      el.briefManagerSuggestion.textContent = (template.suggestions || {}).epic_manager || "";
      el.briefArchitectSuggestion.textContent = (template.suggestions || {}).epic_architect || "";
      el.btnSubmitBrief.disabled = template.tracking_ready === false;
      el.briefStatus.textContent = template.tracking_ready === false
        ? "Install and authenticate gh or glab for this origin before creating a brief."
        : "";
    } catch (err) {
      el.briefStatus.textContent = err.message || "Could not load brief defaults";
      el.briefStatus.classList.add("error");
    }
  }

  async function submitBrief(ev) {
    ev.preventDefault();
    const form = new FormData(el.briefForm);
    const payload = Object.fromEntries(form.entries());
    el.btnSubmitBrief.disabled = true;
    el.briefStatus.classList.remove("error");
    el.briefStatus.textContent = "Creating branch and merge request…";
    try {
      const response = await apiPost("/api/briefs", payload);
      el.briefStatus.textContent = "Brief created. Review and merge it to add it to the backlog.";
      el.briefResult.replaceChildren();
      const link = document.createElement("a");
      link.href = response.body.merge_request_url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = "Open " + response.body.epic_id + " merge request";
      el.briefResult.appendChild(link);
      el.briefResult.hidden = false;
    } catch (err) {
      el.briefStatus.textContent = (err.body && err.body.error) || err.message || "Brief creation failed";
      el.briefStatus.classList.add("error");
    } finally {
      el.btnSubmitBrief.disabled = false;
    }
  }

  async function pullMain() {
    el.btnPullMain.disabled = true;
    el.syncStatus.textContent = "Pulling…";
    try {
      const response = await apiPost("/api/sync/pull", {});
      const added = response.body.new_briefs || [];
      el.syncStatus.textContent = added.length ? "Imported " + added.join(", ") : "Main is current";
      await refreshBoard();
    } catch (err) {
      el.syncStatus.textContent = (err.body && err.body.error) || err.message || "Pull failed";
      el.syncStatus.classList.add("error");
    } finally {
      el.btnPullMain.disabled = false;
    }
  }

  function visibleBoardView(view) {
    if (!view || !BoardFocusApi || !boardFocus) return view;
    return BoardFocusApi.applyBoardLens(view, boardFocus);
  }

  function renderFeaturesLensEmpty(tierEl, empty) {
    if (!tierEl) return;
    const msg = tierEl.querySelector("[data-board-features-lens-empty]");
    if (msg) {
      msg.hidden = !empty;
    }
  }

  function renderTasksLensEmpty(tierEl, empty) {
    if (!tierEl) return;
    const msg = tierEl.querySelector("[data-board-tasks-lens-empty]");
    if (msg) {
      msg.hidden = !empty;
    }
  }

  function completedColumnElements(tierEl) {
    return tierEl.querySelector('[data-column="3_completed"]');
  }

  function renderCompletedColumn(tierEl, tier, visibleView) {
    const columnWrap = completedColumnElements(tierEl);
    if (!columnWrap || !boardFocus || !BoardFocusApi) return;
    const col = "3_completed";
    const colEl = columnWrap.querySelector('[data-column-body="3_completed"]');
    const countEl = columnWrap.querySelector("[data-board-completed-count]");
    const collapseBtn = columnWrap.querySelector("[data-board-completed-collapse]");
    const collapsed = !!boardFocus.completed_collapsed[tier];
    const count = BoardFocusApi.countVisibleInColumn(visibleView, tier, col);

    columnWrap.classList.toggle("board-column-completed-collapsed", collapsed);
    if (countEl) {
      countEl.textContent = count === 1 ? "1 card" : count + " cards";
      countEl.hidden = !collapsed;
    }
    if (collapseBtn) {
      collapseBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      collapseBtn.textContent = collapsed ? "Expand" : "Collapse";
    }
    if (!colEl) return;
    colEl.innerHTML = "";
    if (!collapsed) {
      (visibleView[tier][col] || []).forEach(function (item) {
        colEl.appendChild(buildRow(item, tier, col));
      });
    }
  }

  function renderBoard(view) {
    lastBoardView = view;
    if (BoardFocusApi && boardFocus) {
      boardFocus = BoardFocusApi.reconcileFocusWithLens(view, boardFocus);
    }
    const visibleView = visibleBoardView(view);
    const featuresLensEmpty =
      BoardFocusApi && boardFocus
        ? BoardFocusApi.isFeaturesLensEmpty(view, boardFocus)
        : false;
    const tasksLensEmpty =
      BoardFocusApi && boardFocus ? BoardFocusApi.isTasksLensEmpty(boardFocus) : true;
    ["epics", "features", "tasks"].forEach(function (tier) {
      const tierEl = el.board.querySelector('[data-tier="' + tier + '"]');
      if (!tierEl) return;
      if (tier === "features") {
        renderFeaturesLensEmpty(tierEl, featuresLensEmpty);
      }
      if (tier === "tasks") {
        renderTasksLensEmpty(tierEl, tasksLensEmpty);
      }
      ["1_backlog", "2_active"].forEach(function (col) {
        const colEl = tierEl.querySelector('[data-column="' + col + '"]');
        if (!colEl) return;
        colEl.innerHTML = "";
        (visibleView[tier][col] || []).forEach(function (item) {
          colEl.appendChild(buildRow(item, tier, col));
        });
      });
      renderCompletedColumn(tierEl, tier, visibleView);
    });
  }

  function wireCompletedCollapseControls() {
    if (!el.board || !BoardFocusApi) return;
    el.board.querySelectorAll("[data-board-completed-collapse]").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        const tier = btn.getAttribute("data-board-tier");
        if (!tier || !boardFocus) return;
        boardFocus = BoardFocusApi.toggleCompletedCollapsed(boardFocus, tier);
        if (lastBoardView) {
          renderBoard(lastBoardView);
        }
      });
    });
  }

  function buildRow(item, tier, column) {
    const row = document.createElement("div");
    row.className = "board-row";
    row.dataset.id = item.id;
    row.dataset.tier = item.tier;
    if (item.status === "blocked") {
      row.classList.add("board-row-blocked");
    }
    if (
      tier === "epics" &&
      boardFocus &&
      boardFocus.selected_epic_id === item.id
    ) {
      row.classList.add("board-row-selected");
      row.dataset.boardEpicSelected = "true";
    }
    if (
      tier === "features" &&
      boardFocus &&
      boardFocus.selected_feature_id === item.id
    ) {
      row.classList.add("board-row-selected");
      row.dataset.boardFeatureSelected = "true";
    }

    const title = document.createElement("div");
    title.className = "board-row-title";
    title.textContent = item.id + " — " + item.title;
    row.appendChild(title);

    if (tier === "tasks") {
      const branch = document.createElement("div");
      branch.className = "task-branch";
      branch.textContent = "task/" + item.id;
      row.appendChild(branch);
    }

    const actions = document.createElement("div");
    actions.className = "board-row-actions";

    const startable = OPEN_STATUSES[item.status] === true;
    if (tier === "epics") {
      if (startable) {
        actions.appendChild(actionButton("Activate team", function () {
          return dispatch("/api/activate_epic", { id: item.id });
        }));
      }
      if (column === "2_active") {
        if (item.plan_approved) {
          const approved = actionButton(
            "Approved",
            function () { return Promise.resolve(); },
            "Epic plan approved; eligible features launch automatically."
          );
          approved.classList.add("approval-confirmed");
          actions.appendChild(approved);
        } else {
          actions.appendChild(actionButton("Approve plan", function () {
            return dispatch("/api/approve_epic_plan", { id: item.id });
          }));
        }
        actions.appendChild(actionButton("Close epic", function () {
          return confirmEpicComplete(item.id);
        }));
      }
    }
    if (tier === "features") {
      if (column === "2_active") {
        actions.appendChild(actionButton("Open team", function () {
          return attach(item.id, "feature");
        }));
      }
    }
    if (tier === "tasks") {
      const retryable = column === "2_active" && item.status === "blocked";
      if (column === "2_active" && item.status === "blocked") {
        actions.appendChild(actionButton("Retry", function () {
          return askBoss("task", item.id);
        }));
      }
    }
    if (tier === "epics") {
      actions.appendChild(actionButton("Attach", function () {
        return attach(item.id, "epic");
      }));
    }

    actions.appendChild(actionButton("View plan", function () {
      window.location.assign("/plan/" + item.id);
      return Promise.resolve();
    }));

    if (tier === "epics") {
      row.addEventListener("click", function (ev) {
        if (ev.target.closest(".board-row-actions")) return;
        if (!boardFocus || !BoardFocusApi || !lastBoardView) return;
        boardFocus = BoardFocusApi.toggleEpicSelection(
          boardFocus,
          item.id,
          lastBoardView
        );
        renderBoard(lastBoardView);
        refreshFlightReport();
      });
    }
    if (tier === "features") {
      row.addEventListener("click", function (ev) {
        if (ev.target.closest(".board-row-actions")) return;
        if (!boardFocus || !BoardFocusApi || !lastBoardView) return;
        boardFocus = BoardFocusApi.toggleFeatureSelection(
          boardFocus,
          item.id,
          lastBoardView
        );
        renderBoard(lastBoardView);
      });
    }

    row.appendChild(actions);
    return row;
  }

  function actionButton(label, handler, disabledReason) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    if (disabledReason) {
      btn.disabled = true;
      btn.title = disabledReason;
    }
    btn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      if (btn.disabled) return;
      btn.disabled = true;
      handler()
        .catch(function (err) {
          setStatus(err.message || String(err), true);
        })
        .finally(function () {
          if (btn.isConnected && !disabledReason) btn.disabled = false;
        });
    });
    return btn;
  }

  async function dispatch(path, payload) {
    try {
      const { body } = await apiPost(path, payload);
      if (!body.ok) {
        dispatchBanner = body.reason ? "Dispatch failed: " + body.reason : "Dispatch failed";
        setStatus(dispatchBanner, true);
      } else {
        dispatchBanner = "";
        setStatus("");
      }
      return body;
    } finally {
      await refreshBoard();
    }
  }

  /** Dispatch starts the feature team's first turn (mint tasks); open its room to watch. */
  async function dispatchFeature(id) {
    const before = await fetchChatMessages(id).catch(function () {
      return [];
    });
    const body = await dispatch("/api/dispatch_feature", { id: id });
    if (!body.ok) return body;
    await attach(id, "feature");
    waitForChatReplies(id, countAgentChatMessages(before));
    return body;
  }

  async function askBoss(kind, id) {
    const { status, body } = await apiPost("/api/ask_boss_dispatch", { kind: kind, id: id });
    if (status === 202 && body.ok) {
      setStatus("Ask Boss request queued.");
    }
  }

  async function mergeTask(id) {
    try {
      const { body } = await apiPost("/api/merge_task_branch", { id: id });
      if (body.ok) {
        dispatchBanner = "";
        setStatus(
          "Merged " + id + " (" + (body.branch || "") + ") @ " + (body.merge_sha || ""),
          false
        );
        await refreshBoard();
        await refreshBossView();
      } else {
        setStatus("Merge failed: " + (body.reason || "unknown"), true);
      }
    } catch (err) {
      const reason =
        err.body && err.body.reason ? err.body.reason : err.message || "merge failed";
      setStatus("Merge failed: " + reason, true);
    }
  }

  async function confirmEpicComplete(epicId) {
    try {
      const { body } = await apiPost("/api/confirm_epic_complete", { id: epicId });
      if (body.ok) {
        dispatchBanner = "";
        setStatus("Epic " + epicId + " closed.", false);
        await refreshBoard();
      } else {
        setStatus("Epic close refused: " + (body.reason || "not_ready"), true);
      }
    } catch (err) {
      setStatus(err.message || "Epic close failed", true);
    }
  }

  function renderBossView(summary) {
    if (!el.bossSummary || !summary) return;
    const parts = [
      "slots free: " + summary.slots_free,
      "dispatchable features: " + (summary.dispatchable_features || []).length,
      "dispatchable tasks: " + (summary.dispatchable_tasks || []).length,
      "failed: " + ((summary.failed_tasks || []).join(", ") || "none"),
    ];
    el.bossSummary.textContent = parts.join(" · ");
  }

  async function refreshBossView() {
    try {
      const summary = await apiGet("/api/boss_view");
      renderBossView(summary);
    } catch (_e) {
      /* optional panel */
    }
  }

  function countAgentChatMessages(messages) {
    return (messages || []).filter(function (msg) {
      return AGENT_CHAT_AUTHORS[msg.author];
    }).length;
  }

  let lastChatSnapshot = "";
  let lastChatSnapshotGraphId = null;

  function chatSnapshot(messages) {
    if (!Array.isArray(messages)) return "";
    return messages
      .map(function (msg) {
        return (
          String(msg.id || "") +
          "\t" +
          String(msg.author || "") +
          "\t" +
          String(msg.body || "").length
        );
      })
      .join("\n");
  }

  function renderChatMessages(messages) {
    if (!el.chatMessages) return;
    if (!Array.isArray(messages)) return;
    const snap = chatSnapshot(messages);
    if (snap === lastChatSnapshot && focusGraphId === lastChatSnapshotGraphId) return;
    lastChatSnapshot = snap;
    lastChatSnapshotGraphId = focusGraphId;
    el.chatMessages.innerHTML = "";
    messages.forEach(function (msg) {
      const div = document.createElement("div");
      div.className = "chat-message";
      if (msg.author && msg.author !== "human") {
        div.classList.add("chat-message-agent");
      }
      const author = document.createElement("div");
      author.className = "author";
      author.textContent = msg.author || "unknown";
      const body = document.createElement("div");
      body.className = "chat-body";
      body.textContent = msg.body;
      div.appendChild(author);
      div.appendChild(body);
      el.chatMessages.appendChild(div);
    });
    el.chatMessages.scrollTop = el.chatMessages.scrollHeight;
  }

  let inflightChatFetch = null;
  let inflightChatFetchId = null;

  async function fetchChatMessages(graphId) {
    if (inflightChatFetch && inflightChatFetchId === graphId) {
      return inflightChatFetch;
    }
    inflightChatFetchId = graphId;
    inflightChatFetch = apiGet("/api/chat/" + encodeURIComponent(graphId)).finally(function () {
      if (inflightChatFetchId === graphId) {
        inflightChatFetch = null;
        inflightChatFetchId = null;
      }
    });
    return inflightChatFetch;
  }

  async function loadChat(options) {
    const graphId = focusGraphId;
    if (graphId !== lastChatSnapshotGraphId) {
      lastChatSnapshot = "";
    }
    const userInitiated = !options || options.userInitiated !== false;
    try {
      const messages = await fetchChatMessages(graphId);
      renderChatMessages(messages);
      if (userInitiated) clearChatPollDiagnostic();
      return messages;
    } catch (err) {
      reportChatLoadFailure(err, { userInitiated: userInitiated });
      return [];
    }
  }

  let chatPollInFlight = false;

  /** Background refresh; never updates chat status on failure. */
  async function pollChatSidecar() {
    if (!focusGraphId || chatPollInFlight) return;
    chatPollInFlight = true;
    const graphId = focusGraphId;
    try {
      const messages = await fetchChatMessages(graphId);
      if (graphId !== focusGraphId) return;
      renderChatMessages(messages);
      clearChatPollDiagnostic();
    } catch (err) {
      reportChatLoadFailure(err, { userInitiated: false });
    } finally {
      chatPollInFlight = false;
    }
  }

  async function waitForChatReplies(graphId, baselineAgentCount) {
    const deadline = Date.now() + 120000;
    const team = graphId.indexOf("feat_") === 0 ? "Feature" : "Epic";
    setStatus(team + " team is thinking…", false);
    while (Date.now() < deadline) {
      await new Promise(function (resolve) {
        setTimeout(resolve, 1500);
      });
      if (graphId !== focusGraphId) return;
      try {
        const messages = await fetchChatMessages(graphId);
        if (graphId !== focusGraphId) return;
        renderChatMessages(messages);
        if (countAgentChatMessages(messages) > baselineAgentCount) {
          setStatus("");
          return;
        }
      } catch (_e) {
        /* keep polling */
      }
    }
    setStatus("No team reply yet — check Providers and CURSOR_API_KEY.", true);
  }

  async function attach(graphId, kind) {
    try {
      if (attachedGraphId && attachedGraphId !== graphId) {
        await apiPost("/api/detach", { graph_id: attachedGraphId });
        attachedGraphId = null;
      }
      await apiPost("/api/attach", { graph_id: graphId });
    } catch (err) {
      setStatus(err.message || String(err), true);
      throw err;
    }
    attachedGraphId = graphId;
    focusGraphId = graphId;
    if (kind === "feature" && boardFocus && BoardFocusApi) {
      const view = await apiGet("/api/board");
      lastBoardView = view;
      const featureItem = BoardFocusApi.findFeatureItem(view, graphId);
      if (featureItem) {
        boardFocus = BoardFocusApi.applyFeatureSelection(boardFocus, featureItem);
      }
      renderBoard(view);
    }
    updateFocusUi(kind);
    await loadChat();
    setStatus("Attached to " + graphId + ". You can compose chat.");
  }

  async function detach() {
    if (!attachedGraphId) return;
    await apiPost("/api/detach", { graph_id: attachedGraphId });
    attachedGraphId = null;
    focusGraphId = defaultEpicId;
    updateFocusUi("epic");
    await loadChat();
    setStatus("Detached — Epic War Room.");
  }

  function updateFocusUi(kind) {
    el.chatGraphId.textContent = focusGraphId;
    const attached = attachedGraphId === focusGraphId;
    el.chatBody.disabled = !attached;
    el.chatSend.disabled = !attached;
    el.chatBody.placeholder = attached
      ? "Message…"
      : "Attach to this graph to compose…";

    if (kind === "feature" && attachedGraphId) {
      el.featurePlaceholder.hidden = false;
      el.epicChat.querySelector("h2").textContent = "Feature context";
    } else {
      el.featurePlaceholder.hidden = true;
      el.epicChat.querySelector("h2").textContent = "Epic War Room chat";
    }

    el.attachmentLabel.textContent =
      attachedGraphId && kind === "feature"
        ? "Attached: " + attachedGraphId
        : "Epic War Room";
    el.btnDetach.hidden = !attachedGraphId;
  }

  async function refreshBoard() {
    try {
      const view = await apiGet("/api/board?_=" + Date.now());
      renderBoard(view);
      await refreshFlightReport();
      await refreshBossView();
    } catch (err) {
      reportBoardLoadFailure(err);
    }
  }

  function epicIdForFlightLens() {
    if (boardFocus && boardFocus.selected_epic_id) {
      return boardFocus.selected_epic_id;
    }
    return defaultEpicId;
  }

  function showFlightMessage(message) {
    el.flightBody.innerHTML = "";
    const note = document.createElement("p");
    note.className = "flight-empty";
    note.textContent = message;
    el.flightBody.appendChild(note);
  }

  function renderFlightReport(data, epicId) {
    if (!el.flightPanel || !el.flightBody) return;
    const features = (data.features || []).filter(function (feat) {
      const parentFeat = lastBoardView
        ? BoardFocusApi && BoardFocusApi.findFeatureItem(lastBoardView, feat.work_id)
        : null;
      if (parentFeat && parentFeat.parent === epicId) return true;
      if (!lastBoardView) return true;
      const allFeats = (lastBoardView.features && lastBoardView.features["2_active"]) || [];
      const match = allFeats.find(function (item) {
        return item.id === feat.work_id && item.parent === epicId;
      });
      return !!match;
    });
    const overlaps = (data.overlaps || []).filter(function (row) {
      return (row.work_ids || []).some(function (id) {
        return id === epicId || features.some(function (f) {
          return f.work_id === id;
        });
      });
    });
    if (!features.length && !overlaps.length) {
      el.flightPanel.hidden = false;
      showFlightMessage("Nothing in flight.");
      return;
    }
    el.flightPanel.hidden = false;
    el.flightBody.innerHTML = "";
    features.forEach(function (feat) {
      const block = document.createElement("div");
      block.className = "flight-feature-block";
      const title = document.createElement("div");
      title.className = "flight-feature-title";
      title.textContent = feat.work_id + " (" + feat.branch + ")";
      block.appendChild(title);
      const paths = (data.changed_paths && data.changed_paths[feat.work_id]) || [];
      const pathList = document.createElement("ul");
      pathList.className = "flight-path-list";
      if (!paths.length) {
        const li = document.createElement("li");
        li.textContent = "(no path changes yet)";
        pathList.appendChild(li);
      } else {
        paths.forEach(function (p) {
          const li = document.createElement("li");
          li.textContent = p;
          pathList.appendChild(li);
        });
      }
      block.appendChild(pathList);
      el.flightBody.appendChild(block);
    });
    if (overlaps.length) {
      const hint = document.createElement("div");
      hint.className = "flight-overlap-hint";
      hint.textContent = "Overlapping paths:";
      el.flightBody.appendChild(hint);
      overlaps.forEach(function (row) {
        const line = document.createElement("div");
        line.className = "flight-overlap-row";
        line.textContent =
          (row.work_ids || []).join(" vs ") + ": " + (row.paths || []).join(", ");
        el.flightBody.appendChild(line);
      });
    }
  }

  async function refreshFlightReport() {
    if (!el.flightPanel || !el.flightBody) return;
    const epicId = epicIdForFlightLens();
    const showEpicHome =
      !attachedGraphId || attachedGraphId === defaultEpicId || attachedGraphId === epicId;
    if (!showEpicHome && attachedGraphId && attachedGraphId.indexOf("feat_") === 0) {
      el.flightPanel.hidden = true;
      return;
    }
    try {
      const data = await apiGet("/api/flight");
      renderFlightReport(data, epicId);
    } catch (err) {
      const timedOut = err && (err.name === "TimeoutError" || err.name === "AbortError");
      const msg = timedOut ? "Timed out after 10s" : (err && err.message) || "Load failed";
      el.flightPanel.hidden = false;
      showFlightMessage(msg);
    }
  }

  function setAmendmentStatus(msg, isError) {
    if (!el.amendmentPaneStatus) return;
    el.amendmentPaneStatus.textContent = msg || "";
    el.amendmentPaneStatus.classList.toggle("error", !!isError);
  }

  function renderDiffSplit(text) {
    if (!el.diffBefore || !el.diffAfter) return;
    const beforeLines = [];
    const afterLines = [];
    String(text || "")
      .split("\n")
      .forEach(function (line) {
        if (line.startsWith("+++") || line.startsWith("---") || line.startsWith("@@")) {
          beforeLines.push(line);
          afterLines.push(line);
          return;
        }
        if (line.startsWith("-")) {
          beforeLines.push(line);
          return;
        }
        if (line.startsWith("+")) {
          afterLines.push(line);
          return;
        }
        beforeLines.push(line);
        afterLines.push(line);
      });
    el.diffBefore.innerHTML = beforeLines.map(formatDiffLine).join("\n");
    el.diffAfter.innerHTML = afterLines.map(formatDiffLine).join("\n");
  }

  function formatDiffLine(line) {
    if (line.startsWith("-")) {
      return '<span class="line-remove">' + escapeHtml(line) + "</span>";
    }
    if (line.startsWith("+")) {
      return '<span class="line-add">' + escapeHtml(line) + "</span>";
    }
    return escapeHtml(line);
  }

  function escapeHtml(text) {
    return text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function findAmendment(amdId) {
    return amendments.find(function (row) {
      return row.amd_id === amdId;
    });
  }

  function findAmendmentByDiffPath(diffPath) {
    if (!diffPath) return null;
    return amendments.find(function (row) {
      return row.diff_path === diffPath;
    });
  }

  function hideAmendmentSubforms() {
    if (el.rejectForm) el.rejectForm.hidden = true;
    if (el.reviseForm) el.reviseForm.hidden = true;
  }

  function updateAmendmentActionState(record) {
    const revisePending = record && record.state === "revise_pending";
    if (el.amendmentReviseNotice) {
      el.amendmentReviseNotice.hidden = !revisePending;
    }
    if (el.amendmentActions) {
      el.amendmentActions.hidden = !record || revisePending;
    }
    hideAmendmentSubforms();
  }

  async function selectAmendment(amdId) {
    selectedAmdId = amdId;
    const record = findAmendment(amdId);
    if (!record || !el.amendmentDetail) return;

    Array.from(el.amendmentList.querySelectorAll("li")).forEach(function (node) {
      node.classList.toggle("selected", node.dataset.amdId === amdId);
    });

    el.amendmentDetail.hidden = false;
    el.amendmentMeta.textContent =
      record.amd_id +
      " · " +
      record.feature_id +
      " · section " +
      JSON.stringify(record.section) +
      " · " +
      record.state +
      " — " +
      (record.rationale_summary || "");

    updateAmendmentActionState(record);

    try {
      const resp = await fetch("/api/amendments/" + encodeURIComponent(amdId) + "/diff", {
        signal: deadlineSignal(),
      });
      const text = await resp.text();
      if (!resp.ok) {
        throw new Error(typeof text === "string" ? text : "diff load failed");
      }
      renderDiffSplit(text);
      setAmendmentStatus("");
    } catch (err) {
      const timedOut = err && (err.name === "TimeoutError" || err.name === "AbortError");
      renderDiffSplit("");
      setAmendmentStatus(
        timedOut ? "Timed out after 10s" : err.message || "Could not load diff",
        true
      );
    }
  }

  function renderAmendmentList() {
    if (!el.amendmentList) return;
    el.amendmentList.innerHTML = "";
    if (!amendments.length) {
      setAmendmentStatus("No pending amendments for " + amendmentEpicId + ".");
      if (el.amendmentDetail) el.amendmentDetail.hidden = true;
      selectedAmdId = null;
      return;
    }
    setAmendmentStatus(amendments.length + " pending for " + amendmentEpicId + ".");
    amendments.forEach(function (row) {
      const li = document.createElement("li");
      li.dataset.amdId = row.amd_id;
      li.dataset.diffPath = row.diff_path;
      const idSpan = document.createElement("span");
      idSpan.className = "amd-id";
      idSpan.textContent = row.amd_id;
      li.appendChild(idSpan);
      li.appendChild(
        document.createTextNode(
          " " + row.feature_id + " · " + row.section + " (" + row.state + ")"
        )
      );
      li.addEventListener("click", function () {
        selectAmendment(row.amd_id).catch(function (err) {
          setAmendmentStatus(err.message, true);
        });
      });
      el.amendmentList.appendChild(li);
    });

    let focusId = selectedAmdId;
    if (pendingToastFocus) {
      const byPath = findAmendmentByDiffPath(pendingToastFocus.diff_path);
      if (byPath) {
        focusId = byPath.amd_id;
      }
      pendingToastFocus = null;
    }
    if (focusId && findAmendment(focusId)) {
      selectAmendment(focusId).catch(function (err) {
        setAmendmentStatus(err.message, true);
      });
    } else if (amendments.length === 1) {
      selectAmendment(amendments[0].amd_id).catch(function (err) {
        setAmendmentStatus(err.message, true);
      });
    }
  }

  async function refreshAmendments(focus) {
    if (focus) {
      pendingToastFocus = focus;
      if (focus.epic_id) {
        amendmentEpicId = focus.epic_id;
      }
    }
    try {
      amendments = await apiGet(
        "/api/amendments?epic_id=" + encodeURIComponent(amendmentEpicId)
      );
      if (!Array.isArray(amendments)) {
        amendments = [];
      }
      renderAmendmentList();
    } catch (err) {
      setAmendmentStatus(err.message || "Amendment list failed", true);
    }
  }

  function focusAmendmentPane(focus) {
    if (el.amendmentPane) {
      el.amendmentPane.open = true;
      el.amendmentPane.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
    refreshAmendments(focus);
  }

  async function resolveAmendment(decision, extra) {
    if (!selectedAmdId) return;
    const payload = Object.assign({ decision: decision }, extra || {});
    const { body } = await apiPost(
      "/api/amendments/" + encodeURIComponent(selectedAmdId) + "/resolve",
      payload
    );
    hideAmendmentSubforms();
    if (body.epic_rev) {
      setAmendmentStatus("Accepted — epic_rev " + body.epic_rev);
    } else if (decision === "reject") {
      setAmendmentStatus("Rejected.");
    } else {
      setAmendmentStatus("Counter-proposal sent — awaiting Feature ack.");
    }
    await refreshAmendments();
    await refreshBoard();
  }

  let toastPollInFlight = false;
  let toastHistoryLoaded = false;

  async function pollToasts() {
    if (toastPollInFlight) return;
    toastPollInFlight = true;
    try {
      const data = await apiGet("/api/toasts?after=" + toastOffset);
      if (typeof data.offset === "number" && data.offset > toastOffset) {
        toastOffset = data.offset;
      }
      const replayingHistory = !toastHistoryLoaded;
      toastHistoryLoaded = true;
      const newToasts = data.toasts || [];
      newToasts.forEach(function (toast) {
        const li = document.createElement("li");
        const kind = toast.kind || "event";
        const bodyText = toast.body || "";
        if (kind === "amendment") {
          li.className = "toast-amendment";
        }
        let label = kind + (bodyText ? ": " + bodyText : "");
        if (kind === "orphan" && toast.orphan_id) {
          label = kind + " (" + toast.orphan_id + "): " + bodyText;
        }
        if (kind === "epic_ready_to_close" && toast.epic_id) {
          label = kind + " (" + toast.epic_id + "): " + bodyText;
        }
        if (kind === "flight_overlap" && toast.work_ids && toast.work_ids.length) {
          label =
            kind +
            " (" +
            toast.work_ids.join(" vs ") +
            "): " +
            (toast.paths ? toast.paths.join(", ") : bodyText);
        }
        li.appendChild(document.createTextNode(label));
        if (toast.link) {
          li.appendChild(document.createTextNode(" "));
          const link = document.createElement("a");
          link.href = toast.link;
          link.textContent = toast.link;
          li.appendChild(link);
        }
        if (kind === "amendment") {
          li.addEventListener("click", function () {
            focusAmendmentPane({
              epic_id: toast.epic_id || defaultEpicId,
              diff_path: toast.diff_path,
            });
          });
          if (!replayingHistory) {
            focusAmendmentPane({
              epic_id: toast.epic_id || defaultEpicId,
              diff_path: toast.diff_path,
            });
          }
        }
        el.toastList.prepend(li);
      });
      if (newToasts.length > 0 && !replayingHistory) {
        await refreshBoard();
      }
    } catch (_e) {
      /* ignore transient toast poll errors */
    } finally {
      toastPollInFlight = false;
    }
  }

  function submitChatCompose() {
    if (!el.chatBody) return;
    const body = el.chatBody.value.trim();
    if (!body || !attachedGraphId) return;
    const graphId = attachedGraphId;
    const draft = body;
    el.chatBody.value = "";
    if (el.chatCompose && typeof el.chatCompose.reset === "function") {
      el.chatCompose.reset();
    }
    fetchChatMessages(graphId)
      .catch(function () {
        return [];
      })
      .then(function (before) {
        const baseline = countAgentChatMessages(before);
        return apiPost("/api/chat/" + encodeURIComponent(graphId), { body: draft }).then(
          function () {
            pollChatSidecar();
            return waitForChatReplies(graphId, baseline);
          },
          function (err) {
            if (!el.chatBody.value.trim()) el.chatBody.value = draft;
            throw err;
          }
        );
      })
      .catch(function (err) {
        setStatus(err.message || "Send failed", true);
      });
  }

  if (el.chatCompose) {
    el.chatCompose.addEventListener("submit", function (ev) {
      ev.preventDefault();
      submitChatCompose();
    });
  }
  if (el.chatBody) {
    el.chatBody.addEventListener("keydown", function (ev) {
      if (ev.key !== "Enter" || ev.shiftKey) return;
      if (ev.isComposing) return;
      ev.preventDefault();
      if (el.chatCompose && typeof el.chatCompose.requestSubmit === "function") {
        el.chatCompose.requestSubmit();
      } else {
        submitChatCompose();
      }
    });
  }

  el.btnDetach.addEventListener("click", function () {
    detach().catch(function (err) {
      setStatus(err.message, true);
    });
  });

  if (el.btnAccept) {
    el.btnAccept.addEventListener("click", function () {
      resolveAmendment("accept").catch(function (err) {
        setAmendmentStatus(err.message, true);
      });
    });
  }
  if (el.btnReject) {
    el.btnReject.addEventListener("click", function () {
      hideAmendmentSubforms();
      if (el.rejectForm) el.rejectForm.hidden = false;
    });
  }
  if (el.btnRevise) {
    el.btnRevise.addEventListener("click", function () {
      hideAmendmentSubforms();
      if (el.reviseForm) el.reviseForm.hidden = false;
    });
  }
  if (el.rejectForm) {
    el.rejectForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      const note = el.rejectNote ? el.rejectNote.value.trim() : "";
      resolveAmendment("reject", note ? { note: note } : {})
        .catch(function (err) {
          setAmendmentStatus(err.message, true);
        });
    });
    const cancelReject = el.rejectForm.querySelector(".btn-cancel-reject");
    if (cancelReject) {
      cancelReject.addEventListener("click", function () {
        hideAmendmentSubforms();
      });
    }
  }
  if (el.reviseForm) {
    el.reviseForm.addEventListener("submit", function (ev) {
      ev.preventDefault();
      const revised = el.reviseText ? el.reviseText.value.trim() : "";
      if (!revised) {
        setAmendmentStatus("Revised text is required.", true);
        return;
      }
      const note = el.reviseNote ? el.reviseNote.value.trim() : "";
      const payload = { revised_text: revised };
      if (note) payload.note = note;
      resolveAmendment("revise", payload).catch(function (err) {
        setAmendmentStatus(err.message, true);
      });
    });
    const cancelRevise = el.reviseForm.querySelector(".btn-cancel-revise");
    if (cancelRevise) {
      cancelRevise.addEventListener("click", function () {
        hideAmendmentSubforms();
      });
    }
  }

  function setProvidersStatus(msg, isError) {
    if (!el.providersPaneStatus) return;
    el.providersPaneStatus.textContent = msg || "";
    el.providersPaneStatus.classList.toggle("error", !!isError);
  }

  function authSourceLabel(source) {
    if (source === "env") return "Environment variable";
    if (source === "user-store") return "User store (~/.cascade/credentials)";
    if (source === "cli-session") return "CLI login session";
    return "Not configured";
  }

  function signedInLabel(provider) {
    if (!provider.installed) return "N/A (not installed)";
    if (!provider.authenticated) return "Not signed in";
    if (provider.auth_source === "cli-session") return "Signed in (CLI session)";
    if (provider.auth_source === "env") return "Signed in (environment)";
    if (provider.auth_source === "user-store") return "Signed in (saved token)";
    return "Signed in";
  }

  function renderProviderCard(provider) {
    const card = document.createElement("article");
    card.className = "provider-card";
    card.dataset.providerId = provider.id;

    const title = document.createElement("h3");
    title.className = "provider-id";
    title.textContent = provider.id;
    card.appendChild(title);

    const meta = document.createElement("dl");
    meta.className = "provider-meta";

    function addRow(label, value) {
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      meta.appendChild(dt);
      meta.appendChild(dd);
    }

    addRow("Installed", provider.installed ? "Yes" : "No");
    addRow("Signed in", signedInLabel(provider));
    addRow("Auth source", authSourceLabel(provider.auth_source));
    card.appendChild(meta);

    if (!provider.installed) {
      const missing = document.createElement("p");
      missing.className = "provider-cli-missing";
      missing.textContent =
        "This provider is not installed on this machine.";
      card.appendChild(missing);
      return card;
    }

    if (provider.auth_source === "cli-session") {
      const cliNote = document.createElement("p");
      cliNote.className = "provider-cli-session";
      cliNote.textContent =
        "Already signed in via CLI login on this machine. No pasted token required.";
      card.appendChild(cliNote);
      return card;
    }

    const form = document.createElement("form");
    form.className = "provider-token-form";
    form.addEventListener("submit", function (ev) {
      ev.preventDefault();
      const input = form.querySelector('input[type="password"]');
      const token = input ? input.value.trim() : "";
      if (!token) {
        setProvidersStatus("Token must not be blank", true);
        return;
      }
      apiPost("/api/providers/" + encodeURIComponent(provider.id) + "/token", { token: token })
        .then(function () {
          if (input) input.value = "";
          setProvidersStatus("Token saved for " + provider.id, false);
          return refreshProviders();
        })
        .catch(function (err) {
          setProvidersStatus(err.message || "Save failed", true);
        });
    });

    const label = document.createElement("label");
    label.className = "provider-token-label";
    label.textContent = "API token";
    const input = document.createElement("input");
    input.type = "password";
    input.autocomplete = "off";
    input.placeholder = "Paste token (never echoed by GET)";
    label.appendChild(input);
    form.appendChild(label);

    const actions = document.createElement("div");
    actions.className = "provider-actions";
    const saveBtn = document.createElement("button");
    saveBtn.type = "submit";
    saveBtn.textContent = "Save";
    actions.appendChild(saveBtn);

    const forgetBtn = document.createElement("button");
    forgetBtn.type = "button";
    forgetBtn.className = "btn-provider-forget";
    forgetBtn.textContent = "Forget";
    forgetBtn.addEventListener("click", function () {
      apiPost("/api/providers/" + encodeURIComponent(provider.id) + "/forget", {})
        .then(function () {
          if (input) input.value = "";
          setProvidersStatus("Forgot saved token for " + provider.id, false);
          return refreshProviders();
        })
        .catch(function (err) {
          setProvidersStatus(err.message || "Forget failed", true);
        });
    });
    actions.appendChild(forgetBtn);
    form.appendChild(actions);
    card.appendChild(form);
    return card;
  }

  function renderProviders(data) {
    if (!el.providersList) return;
    el.providersList.innerHTML = "";
    const defaultNote = document.createElement("p");
    defaultNote.className = "providers-default";
    defaultNote.textContent = "Workspace default provider: " + (data.default || "cursor");
    el.providersList.appendChild(defaultNote);
    (data.providers || []).forEach(function (provider) {
      el.providersList.appendChild(renderProviderCard(provider));
    });
  }

  async function refreshProviders() {
    if (!el.providersList) return;
    try {
      const data = await apiGet("/api/providers");
      renderProviders(data);
      setProvidersStatus("", false);
    } catch (err) {
      setProvidersStatus(err.message || "Failed to load providers", true);
    }
  }

  if (el.btnCreateBrief) el.btnCreateBrief.addEventListener("click", openBriefDialog);
  if (el.btnCloseBrief) el.btnCloseBrief.addEventListener("click", function () { el.briefDialog.close(); });
  if (el.btnCancelBrief) el.btnCancelBrief.addEventListener("click", function () { el.briefDialog.close(); });
  if (el.briefForm) el.briefForm.addEventListener("submit", submitBrief);
  if (el.btnPullMain) el.btnPullMain.addEventListener("click", pullMain);

  wireCompletedCollapseControls();
  updateFocusUi("epic");
  refreshBoard();
  refreshFlightReport().catch(reportBoardLoadFailure);
  refreshBossView();
  loadChat({ userInitiated: true }).catch(function (err) {
    reportChatLoadFailure(err, { userInitiated: true });
  });
  refreshAmendments();
  refreshProviders();
  pollToasts();
  setInterval(pollToasts, 2000);
  pollChatSidecar();
  setInterval(pollChatSidecar, 3000);
})();
