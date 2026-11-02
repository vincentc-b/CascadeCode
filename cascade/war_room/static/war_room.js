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
  const BranchSyncUiApi = globalThis.BranchSyncUi;
  const EpicPlanReadinessUi = globalThis.EpicPlanReadinessUi;
  const BriefDefaultsUi = globalThis.BriefDefaultsUi;
  let boardFocus = BoardFocusApi ? BoardFocusApi.defaultBoardFocus() : null;
  let lastBoardView = null;
  let branchSyncRowHelpers = null;

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
    roomSettingsPanel: document.getElementById("room-settings-panel"),
    roomStackedPrEnabled: document.getElementById("room-stacked-pr-enabled"),
    roomSettingsStatus: document.getElementById("room-settings-status"),
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
    openReviewsPane: document.getElementById("open-reviews-pane"),
    openReviewsStatus: document.getElementById("open-reviews-status"),
    openReviewsList: document.getElementById("open-reviews-list"),
    btnRefreshOpenReviews: document.getElementById("btn-refresh-open-reviews"),
    btnCreateBrief: document.getElementById("btn-create-brief"),
    btnPullMain: document.getElementById("btn-pull-main"),
    syncStatus: document.getElementById("sync-status"),
    briefDialog: document.getElementById("brief-dialog"),
    briefDialogTitle: document.getElementById("brief-dialog-title"),
    briefDialogHelp: document.getElementById("brief-dialog-help"),
    briefForm: document.getElementById("brief-form"),
    briefStatus: document.getElementById("brief-status"),
    briefResult: document.getElementById("brief-result"),
    briefProvider: document.getElementById("brief-provider"),
    briefFlexMode: document.getElementById("brief-flex-mode"),
    briefFlexModeWrap: document.getElementById("brief-flex-mode-wrap"),
    briefRoleSelectors: document.getElementById("brief-role-selectors"),
    btnBriefInventoryRetry: document.getElementById("btn-brief-inventory-retry"),
    btnBriefReload: document.getElementById("btn-brief-reload"),
    btnCloseBrief: document.getElementById("btn-close-brief"),
    btnCancelBrief: document.getElementById("btn-cancel-brief"),
    btnSubmitBrief: document.getElementById("btn-submit-brief"),
    supervisorBanner: document.getElementById("supervisor-status-banner"),
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

  function isRoomGraphId(graphId) {
    return graphId.indexOf("epic_") === 0 || graphId.indexOf("feat_") === 0;
  }

  let roomSettingsLoadToken = 0;

  function setRoomSettingsStatus(msg, isError) {
    if (!el.roomSettingsStatus) return;
    el.roomSettingsStatus.textContent = msg || "";
    el.roomSettingsStatus.classList.toggle("error", !!isError);
  }

  async function loadRoomSettings(graphId) {
    if (!el.roomSettingsPanel || !el.roomStackedPrEnabled) return;
    if (!isRoomGraphId(graphId)) {
      el.roomSettingsPanel.hidden = true;
      setRoomSettingsStatus("");
      return;
    }
    el.roomSettingsPanel.hidden = false;
    const token = ++roomSettingsLoadToken;
    el.roomStackedPrEnabled.disabled = true;
    setRoomSettingsStatus("Loading room settings…");
    try {
      const data = await apiGet(
        "/api/room-settings/" + encodeURIComponent(graphId)
      );
      if (token !== roomSettingsLoadToken || graphId !== focusGraphId) return;
      el.roomStackedPrEnabled.checked = !!data.stacked_pr_enabled;
      setRoomSettingsStatus("");
    } catch (err) {
      if (token !== roomSettingsLoadToken) return;
      setRoomSettingsStatus(err.message || "Failed to load room settings", true);
    } finally {
      if (token === roomSettingsLoadToken) {
        el.roomStackedPrEnabled.disabled = false;
      }
    }
  }

  async function saveRoomSettings(enabled) {
    const graphId = focusGraphId;
    if (!isRoomGraphId(graphId) || !el.roomStackedPrEnabled) return;
    el.roomStackedPrEnabled.disabled = true;
    setRoomSettingsStatus("Saving…");
    try {
      const { body: data } = await apiPost("/api/room-settings/" + encodeURIComponent(graphId), {
        stacked_pr_enabled: enabled,
      });
      if (graphId !== focusGraphId) return;
      el.roomStackedPrEnabled.checked = !!data.stacked_pr_enabled;
      setRoomSettingsStatus("");
    } catch (err) {
      setRoomSettingsStatus(err.message || "Failed to save room settings", true);
      await loadRoomSettings(graphId);
    } finally {
      if (graphId === focusGraphId) {
        el.roomStackedPrEnabled.disabled = false;
      }
    }
  }

  function setStatus(msg, isError) {
    el.chatStatus.textContent = msg || dispatchBanner;
    el.chatStatus.classList.toggle("error", !!isError);
  }

  const LOAD_DEADLINE_MS = 10000;
  const EPIC_CLOSE_DEADLINE_MS = 60000;

  function deadlineSignal(timeoutMs) {
    timeoutMs = timeoutMs || LOAD_DEADLINE_MS;
    if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
      return AbortSignal.timeout(timeoutMs);
    }
    const controller = new AbortController();
    setTimeout(function () {
      controller.abort();
    }, timeoutMs);
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

  function supervisorBannerText(health) {
    if (!health || typeof health !== "object") return "";
    const state = health.state;
    const trunkLock = health.trunk_lock_warning;
    const show =
      (typeof trunkLock === "string" && trunkLock.length > 0) ||
      (typeof state === "string" && state.length > 0 && state !== "serving");
    if (!show) return "";
    const parts = [];
    if (state) parts.push("Supervisor: " + state);
    const lastError = health.last_error;
    if (lastError && typeof lastError === "object") {
      const message = lastError.message || lastError.stderr_tail;
      if (message) parts.push(String(message));
    }
    if (health.next_action) parts.push(String(health.next_action));
    if (trunkLock) parts.push("Trunk lock: " + trunkLock);
    return parts.join(" — ");
  }

  function updateSupervisorBanner(health) {
    if (!el.supervisorBanner) return;
    const text = supervisorBannerText(health);
    if (!text) {
      el.supervisorBanner.hidden = true;
      el.supervisorBanner.textContent = "";
      return;
    }
    el.supervisorBanner.textContent = text;
    el.supervisorBanner.hidden = false;
  }

  async function pollSupervisorHealth() {
    try {
      const health = await apiGet("/api/health");
      updateSupervisorBanner(health);
    } catch (_err) {
      /* ignore transient health poll errors */
    }
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

  async function apiPost(path, payload, timeoutMs) {
    const resp = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: deadlineSignal(timeoutMs),
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

  let briefInventory = null;
  let briefTemplate = null;
  let briefSelection = null;
  let briefMode = "create";
  let briefEditTarget = null;
  let briefSubmitInFlight = false;
  let pendingBriefCancels = Object.create(null);
  let pendingBriefCancelLookupOk = false;
  let pendingBriefCancelRefreshAt = 0;
  let pendingBriefCancelRefreshInFlight = null;
  let pendingBriefCancelVersion = 0;
  const submittingBriefCancels = new Set();

  function refreshPendingBriefCancels(force) {
    if (pendingBriefCancelRefreshInFlight) return pendingBriefCancelRefreshInFlight;
    if (!force && Date.now() < pendingBriefCancelRefreshAt) return Promise.resolve();
    const version = pendingBriefCancelVersion;
    pendingBriefCancelRefreshInFlight = apiGet("/api/brief/cancellations")
      .then(function (body) {
        if (version === pendingBriefCancelVersion) {
          pendingBriefCancels = body.reviews || Object.create(null);
        }
        pendingBriefCancelLookupOk = true;
        pendingBriefCancelRefreshAt = version === pendingBriefCancelVersion ? Date.now() + 15000 : 0;
      })
      .catch(function () {
        pendingBriefCancelLookupOk = false;
        pendingBriefCancelRefreshAt = Date.now() + 15000;
      })
      .finally(function () { pendingBriefCancelRefreshInFlight = null; });
    return pendingBriefCancelRefreshInFlight;
  }

  function setBriefInventoryRetryVisible(visible) {
    if (el.btnBriefInventoryRetry) el.btnBriefInventoryRetry.hidden = !visible;
  }

  function setBriefReloadVisible(visible) {
    if (el.btnBriefReload) el.btnBriefReload.hidden = !visible;
  }

  function updateBriefDialogState() {
    if (!BriefDefaultsUi || !briefInventory) {
      if (el.btnSubmitBrief) el.btnSubmitBrief.disabled = true;
      return;
    }
    const trackingReady = briefTemplate ? briefTemplate.tracking_ready : true;
    const status = BriefDefaultsUi.briefStatusMessage(briefInventory, trackingReady);
    el.briefStatus.textContent = status.text;
    el.briefStatus.classList.toggle("error", !!status.error);
    setBriefInventoryRetryVisible(!!status.recoverable);
    if (!briefSelection) {
      el.btnSubmitBrief.disabled = true;
      return;
    }
    el.btnSubmitBrief.disabled = briefSubmitInFlight || !BriefDefaultsUi.canSubmitBrief(briefInventory, briefSelection, trackingReady, briefMode === "edit" ? { allowSavedUnavailable: true, savedSelection: briefEditTarget } : undefined);
  }

  function renderBriefSelectors() {
    if (!BriefDefaultsUi || !briefInventory || !briefSelection) return;
    BriefDefaultsUi.renderFlexModeControl(
      el.briefFlexModeWrap,
      el.briefFlexMode,
      briefInventory,
      briefSelection
    );
    BriefDefaultsUi.renderRoleSelectors(
      el.briefRoleSelectors,
      briefInventory,
      briefTemplate,
      briefSelection,
      {
        onChange: function (role, kind, value) {
          if (kind === "model") {
            briefSelection = BriefDefaultsUi.applyRoleModelChange(
              briefInventory,
              briefSelection,
              role,
              value
            );
          } else {
            briefSelection.reasoning[role] = value;
          }
          renderBriefSelectors();
          updateBriefDialogState();
        },
      },
      { preserveUnavailable: briefMode === "edit" }
    );
  }

  function populateBriefProviders() {
    if (!el.briefProvider || !briefInventory) return;
    el.briefProvider.replaceChildren();
    const providers = (briefInventory.providers || []).slice();
    if (briefMode === "edit" && briefSelection && briefSelection.provider && !providers.some(function (p) { return p.id === briefSelection.provider; })) providers.unshift({ id: briefSelection.provider, display_name: briefSelection.provider + " (saved; unavailable)", models: [] });
    providers.forEach(function (provider) {
      const option = document.createElement("option");
      option.value = provider.id;
      option.textContent = provider.display_name || provider.id;
      option.selected = provider.id === briefSelection.provider;
      el.briefProvider.appendChild(option);
    });
    el.briefProvider.disabled = !(briefInventory.providers || []).length;
  }

  function applyBriefLoadedState() {
    if (!BriefDefaultsUi || !briefInventory || !briefTemplate) return;
    briefSelection = BriefDefaultsUi.initialSelection(briefInventory, briefTemplate, { preserveSaved: briefMode === "edit" });
    if (briefMode === "edit" && briefEditTarget) {
      briefSelection.provider = briefEditTarget.provider;
      briefSelection.models = Object.assign({}, briefEditTarget.models);
      briefSelection.reasoning = Object.assign({}, briefEditTarget.reasoning || {});
      briefSelection.flex_mode = BriefDefaultsUi.normalizeFlexMode(
        briefInventory,
        briefSelection.provider,
        briefEditTarget.flex_mode,
        false
      );
    }
    populateBriefProviders();
    el.briefProvider.onchange = function () {
      briefSelection = BriefDefaultsUi.applyProviderChange(
        briefInventory,
        briefTemplate,
        briefSelection,
        el.briefProvider.value
      );
      renderBriefSelectors();
      updateBriefDialogState();
    };
    renderBriefSelectors();
    updateBriefDialogState();
  }

  async function loadBriefDialogData(forceRefresh) {
    if (!BriefDefaultsUi) {
      throw new Error("Brief defaults UI is unavailable");
    }
    briefInventory = { loading: true, providers: [] };
    briefTemplate = null;
    briefSelection = null;
    populateBriefProviders();
    if (el.briefRoleSelectors) el.briefRoleSelectors.replaceChildren();
    updateBriefDialogState();

    const inventoryUrl = forceRefresh ? "/api/brief/inventory/refresh" : "/api/brief/inventory";
    const inventoryPromise = forceRefresh
      ? apiPost(inventoryUrl, {})
      : apiGet(inventoryUrl);
    const templatePromise = apiGet("/api/brief/template");
    briefInventory = await inventoryPromise;
    if (forceRefresh && briefInventory && briefInventory.body) {
      briefInventory = briefInventory.body;
    }
    briefTemplate = await templatePromise;
    applyBriefLoadedState();
  }

  function resetBriefForm() {
    el.briefForm.reset();
    setBriefReloadVisible(false);
    if (el.briefDialogTitle) el.briefDialogTitle.textContent = briefMode === "edit" ? "Edit backlog brief" : "Create a feature brief";
    if (el.briefDialogHelp) el.briefDialogHelp.textContent = briefMode === "edit" ? "Submit a review request; the approved backlog brief is unchanged until merge and refresh." : "Submitting opens a merge request. Merge it to add the epic to the backlog.";
    if (el.btnSubmitBrief) el.btnSubmitBrief.textContent = briefMode === "edit" ? "Create edit merge request" : "Create merge request";
  }

  function fillBriefForm(data) {
    ["title", "intent", "success_criteria", "constraints", "additional_markdown"].forEach(function (name) { const field = el.briefForm.elements[name]; if (field) field.value = data[name] || ""; });
  }

  async function openBriefEdit(item) {
    briefMode = "edit"; briefEditTarget = null; resetBriefForm(); el.briefResult.hidden = true; el.briefDialog.showModal();
    el.briefStatus.textContent = "Loading saved brief…";
    try {
      const data = await apiGet("/api/brief/edit?epic_id=" + encodeURIComponent(item.id));
      briefEditTarget = { epic_id: data.epic_id, provider: data.provider, models: Object.assign({}, data.models), reasoning: Object.assign({}, data.reasoning || {}), flex_mode: data.flex_mode, source_path: data.source_path, source_revision: data.source_revision };
      fillBriefForm(data); await loadBriefDialogData(false); briefSelection.reasoning = Object.assign({}, data.reasoning || {}); renderBriefSelectors(); updateBriefDialogState();
    } catch (err) { el.briefStatus.textContent = (err.body && err.body.error) || err.message || "Could not load brief"; el.briefStatus.classList.add("error"); }
  }

  async function cancelBacklogEpic(item) {
    if (pendingBriefCancels[item.id] || submittingBriefCancels.has(item.id) || !pendingBriefCancelLookupOk) return;
    const answer = window.prompt("Reason for cancelling " + item.id + "? A review request will be created.");
    if (answer === null) return;
    const reason = answer.trim();
    if (!reason) {
      setStatus("Enter a cancellation reason for " + item.id + ".", true);
      return;
    }
    submittingBriefCancels.add(item.id);
    if (lastBoardView) renderBoard(lastBoardView);
    setStatus("Preparing cancellation review for " + item.id + "…", false);
    try {
      const current = await apiGet("/api/brief/edit?epic_id=" + encodeURIComponent(item.id));
      const response = await apiPost("/api/brief/cancel", {
        epic_id: item.id,
        source_path: current.source_path,
        source_revision: current.source_revision,
        reason: reason,
      });
      pendingBriefCancelVersion += 1;
      pendingBriefCancelRefreshAt = 0;
      pendingBriefCancels[item.id] = { url: response.body.merge_request_url };
      if (lastBoardView) renderBoard(lastBoardView);
      setStatus("Cancellation review created for " + item.id + ". Merge it to cancel the epic.", false);
    } catch (err) {
      if (err.body && err.body.code === "pending_cancel" && err.body.review_url) {
        pendingBriefCancelVersion += 1;
        pendingBriefCancelRefreshAt = 0;
        pendingBriefCancels[item.id] = { url: err.body.review_url };
        if (lastBoardView) renderBoard(lastBoardView);
        setStatus("Cancellation review already awaits approval for " + item.id + ".", false);
        return;
      }
      setStatus((err.body && err.body.error) || err.message || "Could not prepare cancellation review", true);
      if (err.body && err.body.reload) await refreshBoard();
    } finally {
      submittingBriefCancels.delete(item.id);
      if (lastBoardView) renderBoard(lastBoardView);
    }
  }

  async function openBriefDialog() {
    briefMode = "create"; briefEditTarget = null; resetBriefForm();
    el.briefStatus.classList.remove("error");
    el.briefResult.hidden = true;
    setBriefInventoryRetryVisible(false);
    el.briefDialog.showModal();
    el.briefStatus.textContent = "Loading available providers and models…";
    try {
      await loadBriefDialogData(false);
    } catch (err) {
      briefInventory = { loading: false, providers: [], refresh: { failed: true } };
      briefTemplate = briefTemplate || { tracking_ready: true };
      briefSelection = { provider: "", models: {}, reasoning: {} };
      el.briefStatus.textContent = err.message || "Could not load brief defaults";
      el.briefStatus.classList.add("error");
      setBriefInventoryRetryVisible(true);
      el.btnSubmitBrief.disabled = true;
    }
  }

  async function retryBriefInventory() {
    el.briefStatus.classList.remove("error");
    el.briefStatus.textContent = "Refreshing model inventory…";
    setBriefInventoryRetryVisible(false);
    el.btnSubmitBrief.disabled = true;
    try {
      await loadBriefDialogData(true);
    } catch (err) {
      el.briefStatus.textContent = err.message || "Could not refresh model inventory";
      el.briefStatus.classList.add("error");
      setBriefInventoryRetryVisible(true);
      el.btnSubmitBrief.disabled = true;
    }
  }

  async function submitBrief(ev) {
    ev.preventDefault();
    if (!BriefDefaultsUi || !briefInventory || !briefSelection) return;
    const form = new FormData(el.briefForm);
    const fields = Object.fromEntries(form.entries());
    delete fields.provider;
    const payload = briefMode === "edit"
      ? BriefDefaultsUi.buildEditSubmitPayload(fields, briefSelection, briefEditTarget)
      : BriefDefaultsUi.buildSubmitPayload(fields, briefSelection);
    briefSubmitInFlight = true;
    el.btnSubmitBrief.disabled = true;
    el.briefStatus.classList.remove("error");
    el.briefStatus.textContent = "Creating branch and merge request…";
    try {
      const response = await apiPost(briefMode === "edit" ? "/api/brief/edit" : "/api/briefs", payload);
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
      if (err.body && err.body.reload) {
        el.briefStatus.textContent += " Reload the brief to compare, then reapply your edits.";
        setBriefReloadVisible(true);
      }
    } finally {
      briefSubmitInFlight = false;
      updateBriefDialogState();
    }
  }

  async function pullMain() {
    el.btnPullMain.disabled = true;
    el.syncStatus.textContent = "Refreshing briefs…";
    try {
      const response = await apiPost("/api/sync/pull", {});
      const added = response.body.new_briefs || [];
      el.syncStatus.textContent = added.length ? "Imported briefs: " + added.join(", ") : "No new briefs";
      await refreshBoard();
    } catch (err) {
      el.syncStatus.textContent = (err.body && err.body.error) || err.message || "Brief refresh failed";
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

  function unavailableActionLink(label, title) {
    const link = document.createElement("span");
    link.className = "board-action-link board-action-link-unavailable";
    link.setAttribute("role", "link");
    link.setAttribute("aria-disabled", "true");
    link.title = title;
    link.textContent = label;
    return link;
  }

  function renderCompletedEpicsHistory(tierEl, view) {
    if (!tierEl) return;
    const slot = tierEl.querySelector('[data-board-completed-history][data-board-tier="epics"]');
    if (!slot) return;
    slot.innerHTML = "";
    if (!view || !view.board) return;
    const history = view.board.completed_epics_history;
    if (!history) return;
    const label = history.path || "Completed epics history";
    if (history.available && history.url) {
      slot.appendChild(actionLink(label, history.url));
    } else {
      slot.appendChild(
        unavailableActionLink(label, "Repository history link unavailable.")
      );
    }
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
      if (tier === "epics") {
        renderCompletedEpicsHistory(tierEl, view);
      }
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

  function humanizeFeatureReadinessBlocker(raw) {
    if (raw === "not_approved") return null;
    const colon = raw.indexOf(":");
    const prefix = colon >= 0 ? raw.slice(0, colon) : raw;
    const payload = colon >= 0 ? raw.slice(colon + 1) : "";
    switch (prefix) {
      case "unmet_deps":
        return "Unmet dependencies: " + payload;
      case "dispatch_base_unavailable":
        return "Stacked base unavailable: " + payload;
      case "feature_awaiting_merge":
        return "Feature awaiting merge";
      case "sibling_blocked":
        return "Sibling feature blocked";
      case "review_threads_blocking":
        return "Blocking review threads";
      case "epic_inactive":
        return "Epic inactive";
      case "not_in_backlog":
        return "Not in backlog";
      default:
        return raw;
    }
  }

  function appendFeatureReadinessUi(row, actions, item) {
    const readiness = item.readiness;
    if (!readiness) return;

    if (!readiness.approved) {
      const approvalStatus = document.createElement("span");
      approvalStatus.className = "feature-review-status";
      approvalStatus.textContent = "Awaiting feature approval";
      approvalStatus.setAttribute(
        "aria-label",
        "Feature approval status: " + approvalStatus.textContent
      );
      row.appendChild(approvalStatus);
      actions.appendChild(featureApproveActionButton(item));
      return;
    }

    const lines = (readiness.blockers || [])
      .map(humanizeFeatureReadinessBlocker)
      .filter(function (line) { return line; });
    if (!lines.length) return;

    const blockersEl = document.createElement("div");
    blockersEl.className = "feature-readiness-blockers";
    blockersEl.textContent = lines.join(" · ");
    blockersEl.setAttribute("aria-label", "Feature dispatch blockers: " + lines.join("; "));
    row.appendChild(blockersEl);
  }

  function featureApproveActionButton(item) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = "Approve feature";
    btn.addEventListener("click", function (ev) {
      ev.stopPropagation();
      if (btn.disabled) return;
      btn.disabled = true;
      btn.textContent = "Approving…";
      dispatch("/api/approve_feature", { id: item.id })
        .then(function (body) {
          if (body && body.ok && !body.dispatch_pending) {
            setStatus("Feature " + item.id + " approved.", false);
          }
        })
        .catch(function (err) {
          setStatus(err.message || String(err), true);
        })
        .finally(function () {
          if (btn.isConnected) {
            btn.disabled = false;
            btn.textContent = "Approve feature";
          }
        });
    });
    return btn;
  }

  function returnRefusalMessages(eligibility) {
    if (!eligibility || eligibility.eligible || !Array.isArray(eligibility.refusals)) return [];
    return eligibility.refusals
      .map(function (refusal) { return refusal && refusal.message; })
      .filter(function (message) { return typeof message === "string" && message; });
  }

  function appendEpicReturnFeedback(row, eligibility) {
    const messages = returnRefusalMessages(eligibility);
    if (!messages.length) return;
    const feedback = document.createElement("div");
    feedback.className = "epic-return-refusals";
    feedback.textContent = messages.join(" · ");
    feedback.setAttribute("aria-label", "Return to backlog unavailable: " + messages.join("; "));
    row.appendChild(feedback);
  }

  function returnRequestId() {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
      return globalThis.crypto.randomUUID();
    }
    return "return-" + Date.now() + "-" + Math.random().toString(36).slice(2);
  }

  async function returnEpicToBacklog(item) {
    const response = await apiPost("/api/return_epic_to_backlog", {
      epic_id: item.id,
      request_id: returnRequestId(),
    });
    const body = response.body;
    if (body.eligibility) item.return_to_backlog = body.eligibility;
    if (!body.ok) {
      const messages = returnRefusalMessages(body.eligibility);
      setStatus(messages.length ? messages.join(" · ") : (body.message || "Return to backlog was refused."), true);
    } else {
      setStatus("Return to backlog accepted for " + item.id + ".", false);
    }
    await refreshBoard();
    return body;
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

    if (
      tier === "features" &&
      item.review &&
      (item.review.state === "awaiting_review" || item.review.state === "preparing_review")
    ) {
      row.classList.add("board-row-awaiting-review");
      const reviewStatus = document.createElement("span");
      reviewStatus.className = "feature-review-status";
      reviewStatus.textContent =
        item.review.state === "awaiting_review" ? "Awaiting review" : "Preparing review";
      reviewStatus.setAttribute("aria-label", "Feature review status: " + reviewStatus.textContent);
      row.appendChild(reviewStatus);
    }

    const cancellationReview = tier === "epics" && column === "1_backlog"
      ? pendingBriefCancels[item.id] : null;
    if (cancellationReview) {
      row.classList.add("board-row-cancelling");
      const status = document.createElement("span");
      status.className = "epic-cancellation-status";
      status.textContent = "Cancelling · awaiting approval";
      status.setAttribute("aria-label", "Epic cancellation status: awaiting approval");
      row.appendChild(status);
    }

    if (tier === "tasks") {
      const execution = taskExecutionStatus(item);
      const status = document.createElement("span");
      status.className = "task-execution-status task-execution-status-" + execution.kind;
      status.textContent = execution.label;
      status.title = execution.title;
      status.setAttribute("aria-label", "Execution status: " + execution.label);
      row.appendChild(status);

      if (execution.kind === "blocked" && execution.detail) {
        const detail = document.createElement("div");
        detail.className = "task-merge-blocker";
        detail.textContent = execution.detail;
        row.appendChild(detail);
      }

      appendRecoveryFeedback(row, item.recovery);

      const branch = document.createElement("div");
      branch.className = "task-branch";
      branch.textContent = "task/" + item.id;
      row.appendChild(branch);
    }

    if (tier === "epics" && column === "2_active") {
      appendEpicReturnFeedback(row, item.return_to_backlog);
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
        if (
          !item.plan_approved &&
          item.plan_readiness &&
          EpicPlanReadinessUi &&
          EpicPlanReadinessUi.appendPlanEntryStatusToRow
        ) {
          EpicPlanReadinessUi.appendPlanEntryStatusToRow(document, row, item.plan_readiness);
        }
        if (item.plan_approved) {
          const approved = actionButton(
            "Approved",
            function () { return Promise.resolve(); },
            "Epic plan approved; eligible features launch automatically."
          );
          approved.classList.add("approval-confirmed");
          actions.appendChild(approved);
        } else {
          var epicApproveDisabled =
            EpicPlanReadinessUi && EpicPlanReadinessUi.approvePlanDisabledReason
              ? EpicPlanReadinessUi.approvePlanDisabledReason(item.plan_readiness)
              : null;
          var approveBtn = actionButton("Approve plan", function () {
            return dispatch("/api/approve_epic_plan", { id: item.id });
          }, epicApproveDisabled);
          if (epicApproveDisabled && EpicPlanReadinessUi.decorateSemanticallyDisabledButton) {
            EpicPlanReadinessUi.decorateSemanticallyDisabledButton(
              approveBtn,
              epicApproveDisabled,
              null
            );
          }
          actions.appendChild(approveBtn);
        }
        actions.appendChild(actionButton("Close epic", function () {
          return confirmEpicComplete(item.id);
        }));
        const returnEligibility = item.return_to_backlog;
        if (returnEligibility) {
          const refusalMessages = returnRefusalMessages(returnEligibility);
          actions.appendChild(actionButton("Return to backlog", function () {
            return returnEpicToBacklog(item);
          }, returnEligibility.eligible ? null : refusalMessages.join("; ") || "Return to backlog is unavailable."));
        }
      }
    }
    if (tier === "features") {
      appendFeatureReadinessUi(row, actions, item);
      if (column === "2_active") {
        actions.appendChild(actionButton("Open team", function () {
          return attach(item.id, "feature");
        }));
      }
      if (item.review && item.review.url) {
        actions.appendChild(actionLink("Open review", item.review.url));
      }
    }
    if (tier === "tasks") {
      const recovery = item.recovery || {};
      const retryable = recovery.action === "retry" &&
        recovery.terminal_blocker && recovery.terminal_blocker.retryable === true;
      if (column === "2_active") {
        actions.appendChild(actionButton("Merge task", function () {
          return mergeTask(item.id, row);
        }));
        if (retryable) {
          const retry = actionButton("Retry execution", function () {
            return retryTask(item.id);
          });
          retry.classList.add("task-retry-action");
          actions.appendChild(retry);
        }
      }
    }
    if (tier === "epics") {
      if (column === "1_backlog") {
        actions.appendChild(actionButton("Edit", function () { return openBriefEdit(item); }));
        if (cancellationReview) {
          actions.appendChild(actionLink("Open cancellation review", cancellationReview.url));
        } else {
          const cancelDisabled = submittingBriefCancels.has(item.id)
            ? "Preparing cancellation review"
            : !pendingBriefCancelLookupOk ? "Checking cancellation reviews; retry shortly" : null;
          actions.appendChild(actionButton("Cancel", function () { return cancelBacklogEpic(item); }, cancelDisabled));
        }
      }
      actions.appendChild(actionButton("Attach", function () {
        return attach(item.id, "epic");
      }));
    }

    actions.appendChild(actionButton("View plan", function () {
      var planUrl = "/plan/" + item.id;
      if (tier === "epics" || tier === "features") {
        planUrl += "#plan-comments";
      }
      window.location.assign(planUrl);
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

    const syncHelpers = branchSyncHelpers();
    if (syncHelpers) {
      syncHelpers.appendBranchSyncToRow(row, item, column, actions);
    }

    row.appendChild(actions);
    return row;
  }

  function taskExecutionStatus(item) {
    if (item.status === "blocked") {
      return {
        kind: "blocked",
        label: "Blocked",
        title: "Execution stopped and can be retried.",
      };
    }

    const execution = item.execution || {};
    const runtime = String(
      execution.health || execution.phase || item.execution_status ||
      item.runtime_status || item.execution_state || ""
    ).toLowerCase();
    if (runtime === "merge_blocked") {
      const blocker = execution.merge_blocker || {};
      const paths = Array.isArray(blocker.conflict_paths) ? blocker.conflict_paths : [];
      const detail = paths.length ? "Conflicting files: " + paths.join(", ") :
        "Merge refused: " + (blocker.reason || "unknown reason");
      const recovery = blocker.reason === "branch_conflict" ?
        "Resolve the Task branch against its Feature branch, then retry Merge task." :
        "Check the merge refusal, then retry Merge task.";
      return {
        kind: "blocked", label: "Merge blocked", detail: detail,
        title: detail + ". " + recovery,
      };
    }
    if (runtime === "awaiting_merge") {
      return { kind: "queued", label: "Awaiting merge", title: "Validated task is waiting to merge into its Feature branch." };
    }
    if (
      runtime === "stale" || runtime === "stuck" || runtime === "stalled" ||
      runtime === "unhealthy"
    ) {
      return { kind: "stuck", label: "Stuck", title: "Execution needs attention." };
    }
    if (runtime === "queued") {
      return { kind: "queued", label: "Queued", title: "Waiting for an execution slot." };
    }
    if (runtime === "healthy" || runtime === "succeeded") {
      return { kind: "healthy", label: "Healthy", title: "Execution is healthy." };
    }
    if (runtime === "running") {
      return { kind: "running", label: "Running", title: "Execution is in progress." };
    }
    if (runtime === "failed") {
      return { kind: "stuck", label: "Failed", title: "Execution failed and needs attention." };
    }
    if (item.status === "active") {
      return { kind: "idle", label: "No signal", title: "No live execution record is available." };
    }
    return { kind: "idle", label: item.status || "Unknown", title: "No active execution." };
  }

  function appendRecoveryFeedback(row, recovery) {
    if (!recovery || typeof recovery !== "object") return;
    const details = document.createElement("div");
    details.className = "task-recovery-feedback";
    const affected = recovery.affected || {};
    const owner = recovery.owner === null || recovery.owner === undefined || recovery.owner === ""
      ? "unassigned" : String(recovery.owner);
    const target = affected.checkout || affected.branch || "not recorded";
    details.textContent = "Recovery: " + (recovery.phase || "unknown") +
      " · reason: " + (recovery.reason || "unknown") +
      " · attempt " + String(recovery.attempt_count || 0) +
      " · owner: " + owner +
      " · affected: " + target;
    row.appendChild(details);

    if (recovery.next_safe_step) {
      const next = document.createElement("div");
      next.className = "task-recovery-next-step";
      next.textContent = "Next safe step: " + recovery.next_safe_step;
      row.appendChild(next);
    }
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


  function branchSyncHelpers() {
    if (!branchSyncRowHelpers && BranchSyncUiApi && BranchSyncUiApi.createBranchSyncRowHelpers) {
      branchSyncRowHelpers = BranchSyncUiApi.createBranchSyncRowHelpers({
        document: document,
        apiPost: apiPost,
        refreshBoard: refreshBoard,
        setStatus: setStatus,
        actionButton: actionButton,
      });
    }
    return branchSyncRowHelpers;
  }

  function mergeFailureMessage(body) {
    if (BranchSyncUiApi && BranchSyncUiApi.actionableStatusMessage) {
      return BranchSyncUiApi.actionableStatusMessage(body, "Merge failed");
    }
    return "Merge failed: " + ((body && body.reason) || "unknown");
  }

  function epicCloseFailureMessage(body) {
    if (BranchSyncUiApi && BranchSyncUiApi.actionableStatusMessage && body.guidance) {
      return BranchSyncUiApi.actionableStatusMessage(body, "Epic close refused");
    }
    return null;
  }
  function actionLink(label, href) {
    const link = document.createElement("a");
    link.className = "board-action-link";
    link.href = href;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = label;
    link.addEventListener("click", function (ev) {
      ev.stopPropagation();
    });
    return link;
  }

  async function dispatch(path, payload) {
    try {
      const { body } = await apiPost(path, payload);
      if (body.dispatch_pending) {
        dispatchBanner = "Approval saved; dispatch pending: " + (body.dispatch_error || "retrying");
        setStatus(dispatchBanner, true);
      } else if (!body.ok) {
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

  async function retryTask(id) {
    setStatus("Retrying " + id + " through its original execution path…", false);
    try {
      const { body } = await apiPost("/api/retry_task", { id: id });
      if (body.ok) {
        setStatus("Retry started for " + id + ".", false);
      } else {
        const step = body.recovery && body.recovery.next_safe_step;
        setStatus("Retry was not started: " + (step || body.reason || "not retryable"), true);
      }
      return body;
    } catch (err) {
      const step = err.body && err.body.recovery && err.body.recovery.next_safe_step;
      setStatus("Retry failed: " + (step || err.message || String(err)), true);
      throw err;
    } finally {
      await refreshBoard();
    }
  }

  async function mergeTask(id, row) {
    const helpers = branchSyncHelpers();
    try {
      const { body } = await apiPost("/api/merge_task_branch", { id: id });
      if (body.ok) {
        dispatchBanner = "";
        if (helpers && row) helpers.clearRecovery(row);
        setStatus(
          "Merged " + id + " (" + (body.branch || "") + ") @ " + (body.merge_sha || ""),
          false
        );
        await refreshBoard();
      } else {
        if (helpers && row) helpers.showRecovery(row, body);
        setStatus(mergeFailureMessage(body), true);
      }
    } catch (err) {
      const failureBody = err.body || { reason: err.message || "merge failed" };
      if (helpers && row) helpers.showRecovery(row, failureBody);
      setStatus(mergeFailureMessage(failureBody), true);
    }
  }

  async function confirmEpicComplete(epicId) {
    setStatus("Closing epic " + epicId + "…", false);
    try {
      const { body } = await apiPost(
        "/api/confirm_epic_complete",
        { id: epicId },
        EPIC_CLOSE_DEADLINE_MS
      );
      if (body.ok) {
        dispatchBanner = "";
        setStatus("Epic " + epicId + " closed.", false);
        await refreshBoard();
      } else {
        const blockers = (body.blocker_ids || []).join(", ");
        if (body.reason === "open_human_comments") {
          setStatus(
            "Epic close refused: resolve open human comments " + blockers +
              " in " + (body.plan_url || ("/plan/" + epicId + "#plan-comments")),
            true
          );
        } else if (body.reason === "child_features_incomplete") {
          setStatus("Epic close refused: child features incomplete: " + blockers, true);
        } else if (body.reason === "no_child_features") {
          setStatus("Epic close refused: this epic has no child features.", true);
        } else if (body.reason === "pending_feature_review") {
          setStatus("Epic close refused: a child feature review is still pending.", true);
        } else if (body.reason === "pending_epic_review") {
          setStatus("Epic implementation review is pending: " + (body.review_url || "open the review and retry after merge"), false);
        } else if (body.reason === "pending_close_review") {
          setStatus("Epic closeout review is ready: " + (body.review_url || "open the review and retry after merge"), false);
        } else {
          const syncMsg = epicCloseFailureMessage(body);
          setStatus(
            syncMsg || ("Epic close refused: " + (body.reason || "not_ready")),
            true
          );
        }
      }
    } catch (err) {
      const timedOut = err && (err.name === "TimeoutError" || err.name === "AbortError");
      setStatus(timedOut ? "Epic close timed out after 60s" : err.message || "Epic close failed", true);
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
      if (graphId !== focusGraphId) return [];
      renderChatMessages(messages);
      if (userInitiated) clearChatPollDiagnostic();
      return messages;
    } catch (err) {
      if (graphId === focusGraphId) {
        reportChatLoadFailure(err, { userInitiated: userInitiated });
      }
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
      const view = await loadBoardView();
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
    loadRoomSettings(focusGraphId).catch(function (err) {
      setRoomSettingsStatus(err.message || "Failed to load room settings", true);
    });
  }

  let boardRefreshInFlight = null;
  let relatedRefreshInFlight = null;

  /** Share idle reads, but fetch again after an action if an older read is pending. */
  function loadBoardView(forceFresh) {
    if (boardRefreshInFlight) {
      if (forceFresh) {
        return boardRefreshInFlight.catch(function () {}).then(function () {
          return loadBoardView(true);
        });
      }
      return boardRefreshInFlight;
    }
    boardRefreshInFlight = apiGet("/api/board?_=" + Date.now())
      .then(function (view) {
        return refreshPendingBriefCancels(!!forceFresh).then(function () {
          renderBoard(view);
          return view;
        });
      })
      .finally(function () {
        boardRefreshInFlight = null;
      });
    return boardRefreshInFlight;
  }

  function refreshRelatedPanels() {
    if (relatedRefreshInFlight) return relatedRefreshInFlight;
    relatedRefreshInFlight = Promise.all([refreshFlightReport(), refreshBossView()])
      .finally(function () {
        relatedRefreshInFlight = null;
      });
    return relatedRefreshInFlight;
  }

  async function refreshBoard(options) {
    const refreshRelated = !options || options.refreshRelated !== false;
    const forceFresh = !options || options.forceFresh !== false;
    try {
      await loadBoardView(forceFresh);
      if (refreshRelated) {
        await refreshRelatedPanels();
      }
      return true;
    } catch (err) {
      reportBoardLoadFailure(err);
      return false;
    }
  }

  /** Keep lifecycle controls current even when no toast is emitted or a toast is replayed. */
  function pollBoard() {
    return refreshBoard({ refreshRelated: false, forceFresh: false });
  }

  const BOARD_POLL_BASE_MS = 3000;
  const BOARD_POLL_MAX_MS = 30000;
  let boardPollDelayMs = BOARD_POLL_BASE_MS;
  let boardPollTimer = null;

  function scheduleBoardPoll(delayMs) {
    if (boardPollTimer !== null) clearTimeout(boardPollTimer);
    boardPollTimer = setTimeout(async function () {
      boardPollTimer = null;
      if (document.hidden) return;
      const loaded = await pollBoard();
      boardPollDelayMs = loaded
        ? BOARD_POLL_BASE_MS
        : Math.min(BOARD_POLL_MAX_MS, boardPollDelayMs * 2);
      scheduleBoardPoll(boardPollDelayMs);
    }, delayMs);
  }

  function handleVisibilityChange() {
    if (document.hidden) {
      if (boardPollTimer !== null) clearTimeout(boardPollTimer);
      boardPollTimer = null;
      return;
    }
    boardPollDelayMs = BOARD_POLL_BASE_MS;
    scheduleBoardPoll(0);
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

  const OpenReviewsPaneApi = globalThis.OpenReviewsPane;
  const openReviewsPane =
    OpenReviewsPaneApi && OpenReviewsPaneApi.createOpenReviewsPane
      ? OpenReviewsPaneApi.createOpenReviewsPane({
          elements: {
            openReviewsStatus: el.openReviewsStatus,
            openReviewsList: el.openReviewsList,
            btnRefreshOpenReviews: el.btnRefreshOpenReviews,
          },
          apiGet: apiGet,
        })
      : null;

  function setOpenReviewsStatus(msg, isError) {
    if (openReviewsPane) {
      openReviewsPane.setOpenReviewsStatus(msg, isError);
    }
  }

  function refreshOpenReviews(options) {
    if (openReviewsPane) {
      return openReviewsPane.refreshOpenReviews(options);
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
  if (el.btnBriefReload) el.btnBriefReload.addEventListener("click", function () { if (briefEditTarget && briefEditTarget.epic_id) openBriefEdit({ id: briefEditTarget.epic_id }); });
  if (el.btnBriefInventoryRetry) {
    el.btnBriefInventoryRetry.addEventListener("click", function () {
      retryBriefInventory().catch(function (err) {
        el.briefStatus.textContent = err.message || "Could not refresh model inventory";
        el.briefStatus.classList.add("error");
        setBriefInventoryRetryVisible(true);
      });
    });
  }
  if (el.btnCloseBrief) el.btnCloseBrief.addEventListener("click", function () { el.briefDialog.close(); });
  if (el.btnCancelBrief) el.btnCancelBrief.addEventListener("click", function () { el.briefDialog.close(); });
  if (el.briefForm) el.briefForm.addEventListener("submit", submitBrief);
  if (el.btnPullMain) el.btnPullMain.addEventListener("click", pullMain);
  if (el.roomStackedPrEnabled) {
    el.roomStackedPrEnabled.addEventListener("change", function () {
      saveRoomSettings(el.roomStackedPrEnabled.checked).catch(function (err) {
        setRoomSettingsStatus(err.message || "Failed to save room settings", true);
      });
    });
  }
  if (el.btnRefreshOpenReviews) {
    el.btnRefreshOpenReviews.addEventListener("click", function () {
      refreshOpenReviews({ userInitiated: true }).catch(function (err) {
        setOpenReviewsStatus(err.message || "Refresh failed", true);
      });
    });
  }

  async function bootstrapWarRoom() {
    wireCompletedCollapseControls();
    updateFocusUi("epic");

    // Load the board first. It supplies the lens used by flight and avoids a
    // burst of duplicate board/flight/boss requests during startup.
    await refreshBoard();
    await Promise.allSettled([
      loadChat({ userInitiated: true }).catch(function (err) {
        reportChatLoadFailure(err, { userInitiated: true });
      }),
      refreshAmendments(),
      refreshProviders(),
      refreshOpenReviews({ userInitiated: false }),
      pollToasts(),
      pollSupervisorHealth(),
    ]);

    document.addEventListener("visibilitychange", handleVisibilityChange);
    if (!document.hidden) scheduleBoardPoll(boardPollDelayMs);
    setInterval(function () {
      if (!document.hidden) pollSupervisorHealth();
    }, 3000);
    setInterval(function () {
      if (!document.hidden) pollToasts();
    }, 2000);
    setInterval(function () {
      if (!document.hidden) pollChatSidecar();
    }, 3000);
  }

  bootstrapWarRoom().catch(reportLoadFailure);
})();
