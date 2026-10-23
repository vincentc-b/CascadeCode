(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.BranchSyncUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const REASON_LABELS = {
    dirty_index: "Staged changes block update",
    local_changes: "Local changes block update",
    branch_conflict: "Branch conflict",
    merge_conflict: "Merge conflict",
    busy: "Agent turn in progress",
    invariant: "Worktree invariant",
    checkout_missing: "Missing checkout",
    merge_target_missing: "Missing merge target",
    wrong_branch: "Wrong trunk checkout",
    current: "Branch is current",
  };

  function branchSyncSummaryText(sync) {
    if (!sync || !sync.ok) return "";
    const parts = [];
    if (sync.work_branch) parts.push(sync.work_branch);
    if (sync.base_branch) parts.push("← " + sync.base_branch);
    parts.push("+" + sync.ahead + " / −" + sync.behind);
    return parts.join(" · ");
  }

  function shouldShowUpdateBranch(sync) {
    return !!(sync && sync.ok && sync.behind > 0);
  }

  function updateBranchDisabled(sync) {
    return !!(sync && sync.ok && sync.behind > 0 && !sync.update_eligible);
  }

  function updateBranchTooltip(sync) {
    if (!shouldShowUpdateBranch(sync)) return "";
    if (sync.update_eligible) {
      return "Merge the resolved base into this work branch.";
    }
    const reason = sync.update_disabled_reason || "ineligible";
    const label = REASON_LABELS[reason] || reason;
    const guidance = sync.guidance || "";
    return guidance ? label + ": " + guidance : label;
  }

  function formatActionableFailure(body) {
    if (!body || typeof body !== "object") {
      return { summary: "Operation failed", detail: "" };
    }
    const reason = body.reason || "unknown";
    const summary = REASON_LABELS[reason] || String(reason);
    const lines = [];
    if (body.guidance) lines.push(body.guidance);
    if (body.merge_aborted) lines.push("The merge was aborted.");
    if (Array.isArray(body.conflict_paths) && body.conflict_paths.length) {
      lines.push("Blocking paths: " + body.conflict_paths.join(", "));
    }
    return { summary: summary, detail: lines.join(" ") };
  }

  function actionableStatusMessage(body, prefix) {
    const formatted = formatActionableFailure(body);
    const lead = prefix ? prefix + ": " + formatted.summary : formatted.summary;
    return formatted.detail ? lead + " — " + formatted.detail : lead;
  }

  function renderBranchSyncSummary(document, sync) {
    if (!sync) return null;
    const wrap = document.createElement("div");
    wrap.className = "branch-sync-block";
    const summary = document.createElement("div");
    summary.className = "branch-sync-summary";
    if (sync.ok) {
      summary.textContent = branchSyncSummaryText(sync);
      if (sync.base_branch) {
        summary.title = "Resolved base: " + sync.base_branch;
      }
    } else {
      summary.classList.add("branch-sync-summary-error");
      summary.textContent = REASON_LABELS[sync.reason] || sync.reason || "Branch sync unavailable";
      if (sync.guidance) summary.title = sync.guidance;
    }
    wrap.appendChild(summary);
    return wrap;
  }

  function renderRecoveryBlock(document, failureBody) {
    const formatted = formatActionableFailure(failureBody);
    const block = document.createElement("div");
    block.className = "branch-sync-recovery";
    block.setAttribute("role", "status");
    const title = document.createElement("strong");
    title.textContent = formatted.summary;
    block.appendChild(title);
    if (formatted.detail) {
      const detail = document.createElement("span");
      detail.className = "branch-sync-recovery-detail";
      detail.textContent = " " + formatted.detail;
      block.appendChild(detail);
    }
    return block;
  }

  function findUpdateBranchButton(row) {
    if (!row || !row.querySelector) return null;
    return row.querySelector('[data-branch-sync-action="update"]');
  }

  function createBranchSyncRowHelpers(deps) {
    const document = deps.document;
    const apiPost = deps.apiPost;
    const refreshBoard = deps.refreshBoard;
    const setStatus = deps.setStatus;
    const actionButton = deps.actionButton;

    function appendBranchSyncToRow(row, item, column, actionsEl) {
      if (column !== "2_active" || !item.branch_sync) return;

      const syncBlock = renderBranchSyncSummary(document, item.branch_sync);
      if (syncBlock) {
        row.insertBefore(syncBlock, actionsEl);
      }

      if (!shouldShowUpdateBranch(item.branch_sync)) return;

      const disabled = updateBranchDisabled(item.branch_sync);
      const tooltip = updateBranchTooltip(item.branch_sync);
      const btn = actionButton(
        "Update branch",
        function () {
          return runUpdateBranch(item.id, row);
        },
        disabled ? tooltip : null
      );
      btn.dataset.branchSyncAction = "update";
      if (disabled && tooltip) {
        btn.title = tooltip;
      }
      actionsEl.insertBefore(btn, actionsEl.firstChild);
    }

    async function runUpdateBranch(workId, row) {
      let resultBody;
      try {
        const response = await apiPost("/api/update_integration_branch", { id: workId });
        resultBody = response.body;
      } catch (err) {
        resultBody = err.body || { ok: false, reason: err.message || "update_failed" };
      }

      clearRecovery(row);

      if (resultBody && resultBody.ok) {
        setStatus("Branch updated for " + workId + ".", false);
        await refreshBoard();
        return resultBody;
      }

      showRecovery(row, resultBody);
      setStatus(actionableStatusMessage(resultBody, "Update failed"), true);
      return resultBody;
    }

    function clearRecovery(row) {
      if (!row) return;
      const existing = row.querySelector(".branch-sync-recovery");
      if (existing) existing.remove();
    }

    function showRecovery(row, failureBody) {
      if (!row) return;
      clearRecovery(row);
      const block = renderRecoveryBlock(document, failureBody);
      const actions = row.querySelector(".board-row-actions");
      if (actions) {
        row.insertBefore(block, actions);
      } else {
        row.appendChild(block);
      }
    }

    return {
      appendBranchSyncToRow: appendBranchSyncToRow,
      runUpdateBranch: runUpdateBranch,
      showRecovery: showRecovery,
      clearRecovery: clearRecovery,
    };
  }

  return {
    REASON_LABELS: REASON_LABELS,
    branchSyncSummaryText: branchSyncSummaryText,
    shouldShowUpdateBranch: shouldShowUpdateBranch,
    updateBranchDisabled: updateBranchDisabled,
    updateBranchTooltip: updateBranchTooltip,
    formatActionableFailure: formatActionableFailure,
    actionableStatusMessage: actionableStatusMessage,
    renderBranchSyncSummary: renderBranchSyncSummary,
    renderRecoveryBlock: renderRecoveryBlock,
    findUpdateBranchButton: findUpdateBranchButton,
    createBranchSyncRowHelpers: createBranchSyncRowHelpers,
  };
});
