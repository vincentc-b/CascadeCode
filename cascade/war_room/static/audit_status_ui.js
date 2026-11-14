(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.AuditStatusUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function text(value, fallback) {
    return value === null || value === undefined || value === "" ? fallback : String(value);
  }

  function time(value) {
    if (!value) return "Unavailable";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
  }

  function duration(value) {
    return typeof value === "number" && Number.isFinite(value)
      ? value.toFixed(value < 10 ? 2 : 1) + "s"
      : "Unavailable";
  }

  function appendLine(document, parent, label, value, className) {
    const line = document.createElement("p");
    line.className = className || "audit-status-line";
    const strong = document.createElement("strong");
    strong.textContent = label + ": ";
    line.appendChild(strong);
    line.appendChild(document.createTextNode(value));
    parent.appendChild(line);
    return line;
  }

  function compact(value) {
    if (!value || typeof value !== "object") return "Unavailable";
    const entries = Object.keys(value).filter(function (key) { return value[key] !== null; });
    return entries.length ? entries.map(function (key) {
      const item = value[key];
      return key + "=" + (typeof item === "object" ? JSON.stringify(item) : String(item));
    }).join(", ") : "Unavailable";
  }

  function sourceReference(reference) {
    if (!reference || typeof reference !== "object") return "Unavailable";
    const parts = [text(reference.store, "unknown store"), text(reference.row_key, "unknown row")];
    if (reference.incident_history_ordinal !== null && reference.incident_history_ordinal !== undefined) {
      parts.push("incident " + String(reference.incident_history_ordinal));
    }
    return parts.join(" / ");
  }

  function renderCounts(document, parent, counts) {
    const outcomes = counts && counts.by_outcome || {};
    appendLine(document, parent, "Outcomes", [
      "healthy " + (outcomes.healthy || 0),
      "waiting " + (outcomes.expected_wait || 0),
      "incidents " + (outcomes.proven_incident || 0),
      "unavailable " + (outcomes.unavailable_evidence || 0)
    ].join(" · "));
    const tiers = counts && counts.by_tier || {};
    ["task", "feature", "epic"].forEach(function (tier) {
      const row = tiers[tier] || {};
      appendLine(document, parent, tier.charAt(0).toUpperCase() + tier.slice(1), [
        "healthy " + (row.healthy || 0),
        "waiting " + (row.expected_wait || 0),
        "incidents " + (row.proven_incident || 0),
        "unavailable " + (row.unavailable_evidence || 0)
      ].join(" · "), "audit-status-line audit-tier-count");
    });
  }

  function renderIncident(document, incident) {
    const item = document.createElement("li");
    item.className = "audit-incident";
    appendLine(document, item, text(incident.work_id, "Unknown work"),
      text(incident.failure_class, "Unavailable") + " · " + text(incident.verification_status, "Unavailable"),
      "audit-incident-heading");
    appendLine(document, item, "Owner", text(incident.owner, "Unavailable"));
    appendLine(document, item, "Impact / reason", text(incident.reason, "Unavailable"));
    appendLine(document, item, "Occurred", time(incident.occurred_at));
    appendLine(document, item, "Last attempted", time(incident.last_attempted_at));
    appendLine(document, item, "Last verified", time(incident.last_verified_at));
    appendLine(document, item, "Freshness", "fresh until " + time(incident.fresh_until));
    if (incident.next_attempt_at) appendLine(document, item, "Next attempt", time(incident.next_attempt_at));
    if (incident.provenance && incident.provenance.next_action) {
      appendLine(document, item, "Next action", text(incident.provenance.next_action, "Unavailable"));
    }
    appendLine(document, item, "Source", sourceReference(incident.source_ref));
    if (incident.detail_truncated) appendLine(document, item, "Detail", "Truncated at the published evidence bound");
    return item;
  }

  function renderFollowUps(document, container, payload) {
    const investigations = payload && Array.isArray(payload.investigations) ? payload.investigations : [];
    const snapshot = payload && payload.investigation_snapshot || {};
    const heading = document.createElement("h3");
    heading.textContent = "Investigation follow-up (" + investigations.length + ")";
    container.appendChild(heading);
    appendLine(document, container, "Follow-up snapshot",
      text(snapshot.state, "pending") +
      (snapshot.published_at ? " · updated " + time(snapshot.published_at) : "") +
      (snapshot.reason ? " · " + text(snapshot.reason, "Unavailable") : ""));
    appendLine(document, container, "Status boundary",
      "Requests, delivery, acknowledgement and reports coordinate investigation; only VERIFIED current incidents prove incident or resolution.");
    investigations.forEach(function (item) {
      const card = document.createElement("section");
      card.className = "audit-follow-up";
      appendLine(document, card, text(item.work_id, "Unknown work"),
        "owner " + text(item.owner_id, "Unavailable") + " · " + text(item.reason, "Investigation"),
        "audit-incident-heading");
      const source = item.source || {};
      appendLine(document, card, "Investigation request",
        "case " + text(source.case_id, "Unavailable") + " · request " + text(source.request_id, "Unavailable"));
      const request = item.request || {};
      appendLine(document, card, "Delivery",
        text(request.state, "pending") + (request.delivered_at ? " at " + time(request.delivered_at) : "") +
        (request.error ? " · " + text(request.error, "Unavailable") : ""));
      const acknowledgement = item.acknowledgement || {};
      appendLine(document, card, "Acknowledgement",
        text(acknowledgement.state, "pending") +
        (acknowledgement.acknowledged_at ? " at " + time(acknowledgement.acknowledged_at) : ""));
      const report = item.latest_report || {};
      appendLine(document, card, "Latest reported outcome",
        text(report.outcome, "none") + (report.reported_at ? " at " + time(report.reported_at) : ""));
      if (report.finding) appendLine(document, card, "Latest finding", text(report.finding, "Unavailable"));
      if (Array.isArray(report.references) && report.references.length) {
        appendLine(document, card, "Report references", report.references.map(String).join(" · "));
      }
      const reassessment = item.pending_reassessment || {};
      appendLine(document, card, "Next reassessment",
        reassessment.pending ? time(reassessment.next_at) : "Not pending");
      container.appendChild(card);
    });
  }

  function renderCoverageRows(document, parent, rows) {
    while (parent.firstChild) parent.removeChild(parent.firstChild);
    if (!rows.length) {
      appendLine(document, parent, "Coverage details", "No records in the loaded page");
      return;
    }
    const groups = new Map();
    rows.forEach(function (row) {
      const label = row.work_id ? "Work " + String(row.work_id) : "Reason " + text(row.reason, "Unavailable");
      if (!groups.has(label)) groups.set(label, []);
      groups.get(label).push(row);
    });
    groups.forEach(function (records, label) {
      const group = document.createElement("section");
      group.className = "audit-coverage-group";
      const heading = document.createElement("h4");
      heading.textContent = label + " (" + records.length + ")";
      group.appendChild(heading);
      records.forEach(function (row) {
        const record = document.createElement("div");
        record.className = "audit-coverage-record";
        appendLine(document, record, "Status", text(row.verification_status, "Unavailable") + " · " + text(row.reason, "Unavailable"));
        appendLine(document, record, "Owner", text(row.owner, "Unavailable"));
        appendLine(document, record, "Source", sourceReference(row.source_ref));
        group.appendChild(record);
      });
      parent.appendChild(group);
    });
  }

  function renderCoverage(document, container, payload, options) {
    const coverage = payload && payload.coverage || {};
    const statuses = coverage.by_status || {};
    const receipt = payload && payload.receipt || {};
    const snapshot = payload && payload.snapshot || {};
    const heading = document.createElement("h3");
    heading.textContent = "Verification coverage";
    container.appendChild(heading);
    appendLine(document, container, "Coverage",
      "pending " + (statuses.pending || 0) + " · stale " + (statuses.stale || 0) +
      " · unverifiable " + (statuses.unverifiable || 0));
    appendLine(document, container, "Last completed check", time(receipt.last_completed_at || (payload && payload.last_run)));
    appendLine(document, container, "Next scheduled check", time(receipt.next_scheduled_at || (payload && payload.next_due)));
    appendLine(document, container, "Snapshot",
      text(snapshot.state, "pending") + (snapshot.reason ? " · " + text(snapshot.reason, "Unavailable") : ""),
      snapshot.state === "ready" ? "audit-status-line" : "audit-status-line audit-unavailable");
    if (payload && payload.failure) {
      appendLine(document, container, "Audit failure", compact(payload.failure), "audit-status-line audit-unavailable");
    }

    const disclosure = document.createElement("details");
    disclosure.className = "audit-coverage-disclosure";
    const summary = document.createElement("summary");
    summary.textContent = "Show grouped coverage details";
    disclosure.appendChild(summary);
    const body = document.createElement("div");
    body.className = "audit-coverage-details";
    disclosure.appendChild(body);
    container.appendChild(disclosure);
    if (!options || typeof options.loadCoverage !== "function") {
      appendLine(document, body, "Coverage details", "Unavailable");
      return;
    }
    const state = options.state || (options.state = {});
    const epoch = payload && payload.snapshot && payload.snapshot.epoch || null;
    if (state.epoch !== epoch) {
      state.generation = (state.generation || 0) + 1;
      state.epoch = epoch;
      state.loaded = false;
      state.cursor = null;
      state.rows = [];
      state.reloadPending = !!state.open;
    }
    state.rows = state.rows || [];
    state.body = body;
    disclosure.open = !!state.open;
    function paint() {
      renderCoverageRows(document, state.body, state.rows);
      if (state.cursor) {
        const more = document.createElement("button");
        more.type = "button";
        more.className = "btn-secondary audit-coverage-more";
        more.textContent = "Load next coverage page";
        more.addEventListener("click", loadPage);
        state.body.appendChild(more);
      }
    }
    if (state.loaded) paint();
    async function loadPage() {
      if (state.loading) return;
      state.loading = true;
      state.reloadPending = false;
      const generation = state.generation;
      appendLine(document, state.body, "Coverage details", "Loading…");
      try {
        const response = await options.loadCoverage(state.cursor);
        if (generation !== state.generation) return;
        if (!response || response.state !== "ready" || !response.page) {
          while (state.body.firstChild) state.body.removeChild(state.body.firstChild);
          appendLine(document, state.body, "Coverage details",
            "Pending · " + text(response && response.reason, "snapshot unavailable"), "audit-status-line audit-unavailable");
          return;
        }
        if (response.page.epoch && state.epoch && response.page.epoch !== state.epoch) {
          state.generation += 1;
          state.epoch = response.page.epoch;
          state.loaded = false;
          state.cursor = null;
          state.rows = [];
          state.reloadPending = !!state.open;
          return;
        }
        const pageRows = Array.isArray(response.page.rows) ? response.page.rows : [];
        pageRows.forEach(function (row) { state.rows.push(row); });
        state.cursor = response.page.next_cursor || null;
        state.loaded = true;
        paint();
      } catch (err) {
        while (state.body.firstChild) state.body.removeChild(state.body.firstChild);
        appendLine(document, state.body, "Coverage details", err && err.message ? err.message : "Unavailable", "audit-status-line audit-unavailable");
      } finally {
        state.loading = false;
        if (state.reloadPending && state.open) loadPage();
      }
    }
    disclosure.addEventListener("toggle", function () {
      state.open = disclosure.open;
      if (disclosure.open && !state.loaded) {
        loadPage();
      }
    });
    if (state.open && state.reloadPending && !state.loading) loadPage();
  }

  const HISTORY_ROW_LIMIT = 100;

  function historyFilters(state) {
    return {
      work_id: state.workId || "",
      owner: state.owner || "",
      status: state.status || "",
      from: state.from || "",
      to: state.to || ""
    };
  }

  function renderHistoryRow(document, row) {
    const item = document.createElement("li");
    item.className = "audit-history-row";
    appendLine(document, item, text(row.work_id, "Unknown work"),
      text(row.verification_status, "Unavailable") + " · owner " + text(row.owner, "Unavailable"),
      "audit-incident-heading");
    appendLine(document, item, "Occurred", time(row.occurred_at));
    appendLine(document, item, "Last attempted", time(row.last_attempted_at));
    appendLine(document, item, "Last verified", time(row.last_verified_at));
    appendLine(document, item, "Reason", text(row.reason, "Unavailable"));
    appendLine(document, item, "Source", sourceReference(row.source_ref));
    appendLine(document, item, "Legacy provenance", compact(row.provenance));
    if (row.verification_status === "unverifiable") {
      appendLine(document, item, "Historical meaning",
        "Unverifiable previous attempt; this does not prove a current incident or verified resolution.",
        "audit-status-line audit-unavailable");
    } else {
      appendLine(document, item, "Historical meaning",
        "Previous attempt record; current incident and resolution status come from fresh VERIFIED evidence.");
    }
    if (row.detail_truncated) appendLine(document, item, "Detail", "Truncated at the published evidence bound");
    return item;
  }

  function renderHistory(document, container, payload, options) {
    if (!options || typeof options.loadHistory !== "function") return;
    const state = options.state || (options.state = {});
    state.rows = state.rows || [];
    state.generation = state.generation || 0;
    const snapshotEpoch = payload && payload.snapshot && payload.snapshot.epoch || null;
    if (state.epoch !== undefined && state.epoch !== snapshotEpoch) {
      state.generation += 1;
      state.rows = [];
      state.cursor = null;
      state.complete = false;
      state.notice = "Audit snapshot changed. History restarted from the first page.";
      state.reloadPending = !!state.open;
    }
    state.epoch = snapshotEpoch;

    const disclosure = document.createElement("details");
    disclosure.className = "audit-history-disclosure";
    disclosure.open = !!state.open;
    const summary = document.createElement("summary");
    summary.textContent = "Audit history";
    disclosure.appendChild(summary);
    const form = document.createElement("form");
    form.className = "audit-history-filters";
    function input(labelText, name, type) {
      const label = document.createElement("label");
      label.textContent = labelText;
      const control = document.createElement("input");
      control.name = name;
      control.type = type || "text";
      control.value = state[name] || "";
      label.appendChild(control);
      form.appendChild(label);
      return control;
    }
    const controls = {
      workId: input("Exact work ID", "workId"),
      owner: input("Exact owner", "owner"),
      from: input("Occurred from (UTC)", "from", "datetime-local"),
      to: input("Occurred to (UTC)", "to", "datetime-local")
    };
    const statusLabel = document.createElement("label");
    statusLabel.textContent = "Verification status";
    const status = document.createElement("select");
    status.name = "status";
    ["", "proven_incident", "verified", "pending", "stale", "unverifiable"].forEach(function (value) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value || "Any";
      option.selected = state.status === value;
      status.appendChild(option);
    });
    status.value = state.status || "";
    statusLabel.appendChild(status);
    form.appendChild(statusLabel);
    controls.status = status;
    const apply = document.createElement("button");
    apply.type = "submit";
    apply.className = "btn-secondary";
    apply.textContent = "Apply history filters";
    form.appendChild(apply);
    disclosure.appendChild(form);
    const body = document.createElement("div");
    body.className = "audit-history-results";
    disclosure.appendChild(body);
    container.appendChild(disclosure);
    state.body = body;

    function paint() {
      while (state.body.firstChild) state.body.removeChild(state.body.firstChild);
      if (state.notice) appendLine(document, state.body, "History", state.notice, "audit-status-line audit-unavailable");
      if (state.rows.length) {
        const list = document.createElement("ul");
        list.className = "audit-history-list";
        state.rows.forEach(function (row) { list.appendChild(renderHistoryRow(document, row)); });
        state.body.appendChild(list);
      } else if (state.loaded) {
        appendLine(document, state.body, "History", "No records match the applied filters");
      }
      if (!state.complete) {
        const reason = state.reason ? " Reason: " + state.reason + "." : "";
        appendLine(document, state.body, "Continuation",
          (state.cursor ? "More matching history is available." : "History read is incomplete.") + reason,
          "audit-status-line audit-unavailable");
      }
      if (state.cursor && state.rows.length < HISTORY_ROW_LIMIT) {
        const more = document.createElement("button");
        more.type = "button";
        more.className = "btn-secondary audit-history-more";
        more.textContent = "Load next history page";
        more.addEventListener("click", requestPage);
        state.body.appendChild(more);
      } else if (state.cursor) {
        appendLine(document, state.body, "Rendered row bound",
          "100 rows shown. Refine the filters to continue safely.", "audit-status-line audit-unavailable");
      }
    }

    async function requestPage() {
      if (state.loading) {
        state.reloadPending = true;
        return;
      }
      state.loading = true;
      state.reloadPending = false;
      const generation = state.generation;
      const cursor = state.cursor || null;
      appendLine(document, state.body, "History", "Loading…");
      try {
        const response = await options.loadHistory(cursor, historyFilters(state));
        if (generation !== state.generation) return;
        if (response && response.restart) {
          state.generation += 1;
          if (response.epoch) state.epoch = response.epoch;
          state.rows = [];
          state.cursor = null;
          state.complete = false;
          state.notice = "Audit snapshot changed (" + text(response.reason, "epoch changed") + "). History restarted from the first page.";
          state.reloadPending = true;
          return;
        }
        if (!response || response.state !== "ready" || !response.page) {
          state.loaded = true;
          state.complete = false;
          state.reason = text(response && response.reason, "snapshot unavailable");
          paint();
          return;
        }
        const page = response.page;
        const rows = Array.isArray(page.rows) ? page.rows : [];
        rows.slice(0, HISTORY_ROW_LIMIT - state.rows.length).forEach(function (row) { state.rows.push(row); });
        state.cursor = page.next_cursor || null;
        state.complete = page.complete === true;
        state.reason = page.reason || null;
        state.loaded = true;
        if (page.epoch && state.epoch && page.epoch !== state.epoch) {
          state.generation += 1;
          state.epoch = page.epoch;
          state.rows = [];
          state.cursor = null;
          state.complete = false;
          state.notice = "Audit snapshot epoch changed. History restarted from the first page.";
          state.reloadPending = true;
          return;
        }
        paint();
      } catch (err) {
        if (generation !== state.generation) return;
        if (err && err.body && err.body.restart) {
          state.generation += 1;
          if (err.body.epoch) state.epoch = err.body.epoch;
          state.rows = [];
          state.cursor = null;
          state.complete = false;
          state.notice = "Audit snapshot changed (" + text(err.body.reason, "epoch changed") + "). History restarted from the first page.";
          state.reloadPending = true;
        } else {
          state.loaded = true;
          state.complete = false;
          state.reason = err && err.message ? err.message : "Unavailable";
          paint();
        }
      } finally {
        state.loading = false;
        if (state.reloadPending && state.open) requestPage();
      }
    }

    form.addEventListener("submit", function (event) {
      if (event && event.preventDefault) event.preventDefault();
      Object.keys(controls).forEach(function (name) { state[name] = controls[name].value || ""; });
      state.generation += 1;
      state.rows = [];
      state.cursor = null;
      state.complete = false;
      state.loaded = false;
      state.reason = null;
      state.notice = "Applied new history filters; restarted from the first page.";
      state.reloadPending = true;
      if (!state.loading) requestPage();
    });
    disclosure.addEventListener("toggle", function () {
      state.open = disclosure.open;
      if (state.open && !state.loaded) requestPage();
    });
    if (state.loaded || state.notice) paint();
    if (state.open && state.reloadPending && !state.loading) requestPage();
  }

  function render(container, payload, options) {
    if (!container) return;
    const document = container.ownerDocument || globalThis.document;
    while (container.firstChild) container.removeChild(container.firstChild);
    appendLine(document, container, "Last run", time(payload && payload.last_run));
    appendLine(document, container, "Next due", time(payload && payload.next_due));
    appendLine(document, container, "Duration", duration(payload && payload.duration_seconds));
    renderCounts(document, container, payload && payload.counts);
    const current = payload && payload.current || {};
    const incidents = Array.isArray(current.rows) ? current.rows : [];
    const heading = document.createElement("h3");
    heading.textContent = "VERIFIED current incidents (" + incidents.length + ")";
    container.appendChild(heading);
    if (incidents.length) {
      const list = document.createElement("ul");
      list.className = "audit-incident-list";
      incidents.forEach(function (incident) { list.appendChild(renderIncident(document, incident)); });
      container.appendChild(list);
    } else {
      const snapshotReady = payload && payload.snapshot && payload.snapshot.state === "ready";
      const statuses = payload && payload.coverage && payload.coverage.by_status || {};
      const incomplete = !snapshotReady || current.complete === false || !!current.next_cursor ||
        (statuses.pending || 0) + (statuses.stale || 0) + (statuses.unverifiable || 0) > 0;
      appendLine(document, container, "Incidents",
        "No VERIFIED current incidents" + (incomplete ? "; coverage incomplete." : "."));
    }
    if (current.complete === false || current.next_cursor) {
      appendLine(document, container, "Current incidents", "Additional VERIFIED current incidents are available on a continuation page.",
        "audit-status-line audit-unavailable");
    }
    options = options || {};
    const uiState = options.state || (options.state = {});
    uiState.coverage = uiState.coverage || {};
    uiState.history = uiState.history || {};
    renderCoverage(document, container, payload, {
      loadCoverage: options.loadCoverage,
      state: uiState.coverage
    });
    renderFollowUps(document, container, payload);
    const unavailable = payload && Array.isArray(payload.unavailable_evidence)
      ? payload.unavailable_evidence : [];
    if (unavailable.length) {
      appendLine(document, container, "Unavailable evidence",
        unavailable.map(function (item) { return text(item.source, "unknown") + ": " + text(item.reason, "Unavailable"); }).join(" · "),
        "audit-status-line audit-unavailable");
    }
    renderHistory(document, container, payload, {
      loadHistory: options.loadHistory,
      state: uiState.history
    });
  }

  function bindRunControl(options) {
    const button = options.button;
    const status = options.status;
    let submitting = false;

    function show(message, isError) {
      if (!status) return;
      status.textContent = message;
      status.classList.toggle("error", !!isError);
    }

    async function submit() {
      if (submitting) return;
      submitting = true;
      button.disabled = true;
      show("Requesting health audit…", false);
      try {
        const response = await options.request();
        const admission = response && response.body && response.body.status;
        if (admission === "admitted") {
          show("Health audit admitted. Completion is pending; durable status will update below.", false);
        } else if (admission === "coalesced") {
          show("Health audit already pending or running. Completion is pending; durable status will update below.", false);
        } else {
          show("Health audit returned an unknown admission status.", true);
        }
        if (options.refresh) await options.refresh();
      } catch (err) {
        show(err && err.message ? err.message : "Health audit unavailable", true);
      } finally {
        submitting = false;
        button.disabled = false;
      }
    }

    if (button) button.addEventListener("click", submit);
    return { submit: submit };
  }

  return { render: render, renderIncident: renderIncident, renderHistoryRow: renderHistoryRow, bindRunControl: bindRunControl };
});
