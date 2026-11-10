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
      text(incident.failure_class, "Unavailable") + " · " + text(incident.outcome, "Unavailable"),
      "audit-incident-heading");
    appendLine(document, item, "Owner", text(incident.owner, "Unavailable"));
    const evidence = incident.evidence || {};
    appendLine(document, item, "Evidence", evidence.available ? compact(evidence.value) : "Unavailable");
    const request = incident.request || {};
    appendLine(document, item, "Request", text(request.state, "unavailable") + " · " + compact(request.value));
    const acknowledgement = incident.acknowledgement || {};
    appendLine(document, item, "Acknowledgement", acknowledgement.available ? compact(acknowledgement.value) : "Unavailable");
    const result = incident.result || {};
    appendLine(document, item, "Result", result.available ? compact(result.value) : "Pending");
    const retry = incident.retry || {};
    appendLine(document, item, "Retry / cooldown",
      text(retry.state, "Unavailable") + " until " + time(retry.cooldown_until) +
      " · claim expires " + time(retry.claim_expires_at) +
      " · reassess " + time(retry.next_reassessment_at) +
      " · " + compact(retry.policy));
    const resume = incident.resume_action || {};
    appendLine(document, item, "Resume action",
      text(resume.operation, "Unavailable") + " by " + text(resume.owner, "Unavailable"));
    return item;
  }

  function render(container, payload) {
    if (!container) return;
    const document = container.ownerDocument || globalThis.document;
    while (container.firstChild) container.removeChild(container.firstChild);
    appendLine(document, container, "Last run", time(payload && payload.last_run));
    appendLine(document, container, "Next due", time(payload && payload.next_due));
    appendLine(document, container, "Duration", duration(payload && payload.duration_seconds));
    renderCounts(document, container, payload && payload.counts);
    const investigations = payload && Array.isArray(payload.investigations) ? payload.investigations : [];
    const agentHeading = document.createElement("h3");
    agentHeading.textContent = "Agent investigations (" + investigations.length + ")";
    container.appendChild(agentHeading);
    appendLine(document, container, "Agent review",
      "Teams investigate progress, logs and unexpected failures. Delivery is not proof of repair.");
    const agentSchedule = payload && payload.agent_schedule;
    if (agentSchedule) {
      const admission = agentSchedule.admission;
      if (admission && admission.reason) appendLine(document, container, "Automatic agent review",
        admission.reason === "no_live_work" ? "Idle: no active or blocked work" :
        admission.reason === "grace_period" ? "Waiting: live work must be at least 20 minutes old" :
        "Eligible: live work has passed the 20-minute grace period");
      appendLine(document, container, "Next agent review", time(agentSchedule.next_due ? new Date(agentSchedule.next_due * 1000).toISOString() : null));
      if (agentSchedule.last_error) appendLine(document, container, "Agent delivery issue", JSON.stringify(agentSchedule.last_error));
    }
    investigations.forEach(function (item) {
      appendLine(document, container, text(item.work_id, "Unknown work"),
        text(item.reason, "Investigation") + " · " + text(item.status, "pending") +
        " · owner " + text(item.owner_id, "unavailable"));
      const reports = Array.isArray(item.reports) ? item.reports : [];
      const report = reports.length ? reports[reports.length - 1] : null;
      if (report) appendLine(document, container, "Latest finding",
        text(report.outcome, "investigating") + " · " + text(report.finding, "No finding recorded"));
      if (item.delivery_error) appendLine(document, container, "Delivery issue", text(item.delivery_error, "Unavailable"));
      appendLine(document, container, "Next reassessment", time(item.next_reassessment_at));
    });
    const incidents = payload && Array.isArray(payload.incidents) ? payload.incidents : [];
    const heading = document.createElement("h3");
    heading.textContent = "Active incidents (" + incidents.length + ")";
    container.appendChild(heading);
    if (incidents.length) {
      const list = document.createElement("ul");
      list.className = "audit-incident-list";
      incidents.forEach(function (incident) { list.appendChild(renderIncident(document, incident)); });
      container.appendChild(list);
    } else {
      appendLine(document, container, "Incidents", "None active");
    }
    const unavailable = payload && Array.isArray(payload.unavailable_evidence)
      ? payload.unavailable_evidence : [];
    if (unavailable.length) {
      appendLine(document, container, "Unavailable evidence",
        unavailable.map(function (item) { return text(item.source, "unknown") + ": " + text(item.reason, "Unavailable"); }).join(" · "),
        "audit-status-line audit-unavailable");
    }
    if (payload && payload.failure) {
      appendLine(document, container, "Audit failure", compact(payload.failure), "audit-status-line audit-unavailable");
    }
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

  return { render: render, renderIncident: renderIncident, bindRunControl: bindRunControl };
});
