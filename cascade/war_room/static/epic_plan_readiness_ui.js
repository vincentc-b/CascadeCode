(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.EpicPlanReadinessUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const DISABLED_REASON_LABELS = {
    missing_epic_manager_sign_off:
      "Epic Manager must sign off on the current plan revision.",
    missing_epic_architect_sign_off:
      "Epic Architect must sign off on the current plan revision.",
    unresolved_open_questions: "Resolve all open questions before approval.",
    canonical_revision_unavailable:
      "Plan revision is unavailable; refresh and try again.",
    not_ready_for_review: "Plan is not ready for approval.",
  };

  function humanizeApproveDisabledReason(reason) {
    if (reason == null || reason === "") {
      return DISABLED_REASON_LABELS.not_ready_for_review;
    }
    return DISABLED_REASON_LABELS[reason] || String(reason);
  }

  function planEntryStatusLabel(readiness) {
    if (!readiness) return null;
    if (readiness.status === "ready_for_review") return "Ready for review";
    return "Planning in progress";
  }

  function approvePlanDisabledReason(readiness) {
    if (!readiness || readiness.can_approve_plan) return null;
    return humanizeApproveDisabledReason(readiness.approve_disabled_reason);
  }

  function prefersReducedMotion() {
    if (typeof matchMedia !== "function") return false;
    return matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function createPlanEntryStatus(document, readiness) {
    if (!readiness) return null;
    const label = planEntryStatusLabel(readiness);
    if (!label) return null;

    const wrap = document.createElement("span");
    wrap.className =
      "epic-plan-readiness-status epic-plan-readiness-status-" +
      (readiness.status === "ready_for_review" ? "ready" : "planning");
    wrap.setAttribute("role", "status");
    wrap.setAttribute("aria-label", "Epic plan readiness: " + label);

    if (readiness.status === "ready_for_review") {
      const mark = document.createElement("span");
      mark.className = "epic-plan-readiness-ready-mark";
      mark.setAttribute("aria-hidden", "true");
      mark.textContent = "✓";
      wrap.appendChild(mark);
    } else {
      const indicator = document.createElement("span");
      indicator.className = "epic-plan-readiness-indicator";
      indicator.setAttribute("aria-hidden", "true");
      if (prefersReducedMotion()) {
        indicator.classList.add("epic-plan-readiness-indicator-static");
      }
      wrap.appendChild(indicator);
    }

    const text = document.createElement("span");
    text.className = "epic-plan-readiness-label";
    text.textContent = label;
    wrap.appendChild(text);

    return wrap;
  }

  function appendPlanEntryStatusToRow(document, row, readiness) {
    if (!readiness || !row) return null;
    const status = createPlanEntryStatus(document, readiness);
    if (status) row.appendChild(status);
    return status;
  }

  function decorateSemanticallyDisabledButton(btn, disabledReason, reasonElementId) {
    if (!btn || !disabledReason) return;
    btn.disabled = true;
    btn.setAttribute("aria-disabled", "true");
    btn.title = disabledReason;
    if (reasonElementId) {
      btn.setAttribute("aria-describedby", reasonElementId);
    }
  }

  function createDisabledReasonNote(document, epicId, disabledReason) {
    if (!disabledReason) return null;
    const note = document.createElement("span");
    note.className = "epic-plan-approve-disabled-reason";
    note.id = "epic-approve-disabled-reason-" + epicId;
    note.textContent = disabledReason;
    return note;
  }

  function renderPlanReadinessBar(document, readiness, epicId) {
    const bar = document.createElement("div");
    bar.className = "epic-plan-readiness-bar";
    bar.setAttribute("role", "region");
    bar.setAttribute("aria-label", "Epic plan approval readiness");

    const statusSlot = document.createElement("div");
    statusSlot.className = "epic-plan-readiness-bar-status";
    const status = createPlanEntryStatus(document, readiness);
    if (status) statusSlot.appendChild(status);
    bar.appendChild(statusSlot);

    const actions = document.createElement("div");
    actions.className = "epic-plan-readiness-bar-actions";

    const disabledReason = approvePlanDisabledReason(readiness);
    const reasonNote = createDisabledReasonNote(document, epicId, disabledReason);
    if (reasonNote) actions.appendChild(reasonNote);

    const approveBtn = document.createElement("button");
    approveBtn.type = "button";
    approveBtn.className = "epic-plan-readiness-approve";
    approveBtn.textContent = "Approve plan";
    approveBtn.dataset.epicId = epicId;
    decorateSemanticallyDisabledButton(
      approveBtn,
      disabledReason,
      reasonNote ? reasonNote.id : null
    );
    actions.appendChild(approveBtn);
    bar.appendChild(actions);

    const errorEl = document.createElement("p");
    errorEl.className = "epic-plan-readiness-error";
    errorEl.setAttribute("role", "alert");
    errorEl.hidden = true;
    bar.appendChild(errorEl);

    return {
      bar: bar,
      approveButton: approveBtn,
      errorElement: errorEl,
      disabledReasonNote: reasonNote,
    };
  }

  function applyReadinessToPlanBar(chrome, document, readiness, epicId) {
    if (!chrome || !readiness) return;
    const statusSlot = chrome.bar.querySelector(".epic-plan-readiness-bar-status");
    if (statusSlot) {
      statusSlot.replaceChildren();
      const status = createPlanEntryStatus(document, readiness);
      if (status) statusSlot.appendChild(status);
    }

    const disabledReason = approvePlanDisabledReason(readiness);
    if (chrome.disabledReasonNote) {
      chrome.disabledReasonNote.textContent = disabledReason || "";
      chrome.disabledReasonNote.hidden = !disabledReason;
    } else if (disabledReason) {
      const note = createDisabledReasonNote(document, epicId, disabledReason);
      const actions = chrome.bar.querySelector(".epic-plan-readiness-bar-actions");
      if (note && actions) {
        actions.insertBefore(note, chrome.approveButton);
        chrome.disabledReasonNote = note;
      }
    }

    chrome.approveButton.disabled = !!disabledReason;
    if (disabledReason) {
      chrome.approveButton.setAttribute("aria-disabled", "true");
      chrome.approveButton.title = disabledReason;
      if (chrome.disabledReasonNote) {
        chrome.approveButton.setAttribute("aria-describedby", chrome.disabledReasonNote.id);
      }
    } else {
      if (typeof chrome.approveButton.removeAttribute === "function") {
        chrome.approveButton.removeAttribute("aria-disabled");
        chrome.approveButton.removeAttribute("aria-describedby");
      }
      chrome.approveButton.title = "";
    }
  }

  function staleApprovalErrorMessage(err) {
    if (err && err.message) return err.message;
    return "Plan approval was rejected.";
  }

  return {
    DISABLED_REASON_LABELS: DISABLED_REASON_LABELS,
    humanizeApproveDisabledReason: humanizeApproveDisabledReason,
    planEntryStatusLabel: planEntryStatusLabel,
    approvePlanDisabledReason: approvePlanDisabledReason,
    prefersReducedMotion: prefersReducedMotion,
    createPlanEntryStatus: createPlanEntryStatus,
    appendPlanEntryStatusToRow: appendPlanEntryStatusToRow,
    decorateSemanticallyDisabledButton: decorateSemanticallyDisabledButton,
    renderPlanReadinessBar: renderPlanReadinessBar,
    applyReadinessToPlanBar: applyReadinessToPlanBar,
    staleApprovalErrorMessage: staleApprovalErrorMessage,
  };
});
