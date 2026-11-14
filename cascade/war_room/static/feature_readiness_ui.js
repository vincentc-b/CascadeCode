(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.FeatureReadinessUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SUMMARY_LABELS = {
    needs_action: "Needs your action",
    waiting: "Waiting",
    ready_awaiting_dispatch: "Ready, awaiting dispatch",
    unavailable: "Readiness unavailable",
  };

  function primaryReason(explanation) {
    if (!explanation || !Array.isArray(explanation.reasons)) return null;
    return explanation.reasons.find(function (reason) {
      return reason.code === explanation.primary_reason_code;
    }) || null;
  }

  function summaryText(explanation) {
    if (!explanation) return null;
    const label = SUMMARY_LABELS[explanation.summary] || "Readiness unavailable";
    const reason = primaryReason(explanation);
    return reason && reason.message ? label + " — " + reason.message : label;
  }

  function appendWorkIds(document, host, workIds) {
    if (!Array.isArray(workIds) || !workIds.length) return;
    const affected = document.createElement("span");
    affected.className = "feature-readiness-affected";
    affected.textContent = " Affected: " + workIds.join(", ") + ".";
    host.appendChild(affected);
  }

  function appendReason(document, list, reason) {
    const item = document.createElement("li");
    const message = document.createElement("span");
    message.textContent = reason.message || "Required readiness evidence is missing.";
    item.appendChild(message);
    appendWorkIds(document, item, reason.affected_work_ids);

    if (reason.next_action) {
      const next = document.createElement("span");
      next.className = "feature-readiness-next-action";
      next.textContent = " Next: " + reason.next_action;
      item.appendChild(next);
    }

    if (Array.isArray(reason.links) && reason.links.length) {
      const links = document.createElement("span");
      links.className = "feature-readiness-links";
      reason.links.forEach(function (link, index) {
        if (!link || !link.href || !link.label) return;
        if (index > 0) links.appendChild(document.createTextNode(" · "));
        const anchor = document.createElement("a");
        anchor.href = link.href;
        anchor.textContent = link.label;
        links.appendChild(anchor);
      });
      item.appendChild(links);
    }
    list.appendChild(item);
  }

  function appendSection(document, body, headingText, className, rows, appendRow) {
    if (!Array.isArray(rows) || !rows.length) return;
    const heading = document.createElement("h5");
    heading.textContent = headingText;
    body.appendChild(heading);
    const list = document.createElement("ul");
    list.className = className;
    rows.forEach(function (row) { appendRow(document, list, row); });
    body.appendChild(list);
  }

  function appendSatisfied(document, list, prerequisite) {
    const item = document.createElement("li");
    item.textContent = prerequisite.message || "Prerequisite satisfied.";
    appendWorkIds(document, item, prerequisite.affected_work_ids);
    list.appendChild(item);
  }

  function appendAttempt(document, body, attempt) {
    if (!attempt) return;
    const heading = document.createElement("h5");
    heading.textContent = "Last dispatch attempt";
    body.appendChild(heading);
    const context = document.createElement("p");
    context.className = "feature-readiness-attempt";
    const history = attempt.historical
      ? "Historical; readiness has changed since this attempt."
      : attempt.history_state === "unverifiable"
        ? "Current comparison is unavailable."
        : "Compared with the current readiness sources.";
    const outcome = attempt.outcome === "started" ? "started" : "refused";
    context.textContent = "Attempt " + outcome + (attempt.at ? " at " + attempt.at : "") + ". " + history;
    if (attempt.detail) context.textContent += " " + attempt.detail;
    body.appendChild(context);
  }

  function render(document, readiness, featureId) {
    const explanation = readiness && readiness.explanation;
    if (!explanation || explanation.version !== 1) return null;

    const wrap = document.createElement("section");
    wrap.className = "feature-readiness feature-readiness-" +
      (SUMMARY_LABELS[explanation.summary] ? explanation.summary : "unavailable");
    wrap.setAttribute("aria-label", "Activation readiness for " + featureId);

    const summary = document.createElement("p");
    summary.className = "feature-readiness-summary";
    summary.setAttribute("role", "status");
    summary.textContent = summaryText(explanation);
    wrap.appendChild(summary);

    const primary = primaryReason(explanation);
    const additional = (explanation.reasons || []).filter(function (reason) {
      return !primary || reason !== primary;
    });
    const satisfied = Array.isArray(explanation.satisfied) ? explanation.satisfied : [];
    const attempt = explanation.last_dispatch_attempt || null;
    if (!primary && !additional.length && !satisfied.length && !attempt) return wrap;

    const details = document.createElement("details");
    details.className = "feature-readiness-details";
    details.addEventListener("click", function (event) { event.stopPropagation(); });
    const detailsSummary = document.createElement("summary");
    detailsSummary.textContent = "Readiness details";
    detailsSummary.setAttribute("aria-label", "Show activation readiness details for " + featureId);
    details.appendChild(detailsSummary);

    const body = document.createElement("div");
    body.className = "feature-readiness-details-body";
    appendSection(document, body, "Primary reason", "feature-readiness-reasons", primary ? [primary] : [], appendReason);
    appendSection(document, body, "Additional reasons", "feature-readiness-reasons", additional, appendReason);
    appendSection(document, body, "Satisfied prerequisites", "feature-readiness-satisfied", satisfied, appendSatisfied);
    appendAttempt(document, body, attempt);
    details.appendChild(body);
    wrap.appendChild(details);
    return wrap;
  }

  return {
    SUMMARY_LABELS: SUMMARY_LABELS,
    primaryReason: primaryReason,
    summaryText: summaryText,
    render: render,
  };
});
