(function (root, factory) {
  const api = factory(root.BriefDefaultsUi);
  if (typeof module !== "undefined" && module.exports) {
    module.exports = factory(require("./brief_defaults_ui.js"));
  }
  root.ProviderRecoveryDialogUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function (selectors) {
  const TIER_ROLES = {
    epic: ["epic_manager", "epic_architect"],
    feature: ["feature_lead", "feature_architect"],
    task: ["swe"],
  };

  function rolesForTier(tier) {
    return (TIER_ROLES[tier] || []).slice();
  }

  function templateForSelection(selection) {
    return {
      saved: selection || { provider: "", models: {}, reasoning: {}, flex_mode: false },
      provider_models: {},
      suggestions: {},
    };
  }

  function initialSelection(inventory, saved, tier) {
    const roles = rolesForTier(tier);
    const selection = selectors.initialSelection(
      inventory,
      templateForSelection(saved),
      { preserveSaved: true, roles: roles }
    );
    selection.provider = (saved && saved.provider) || selection.provider;
    roles.forEach(function (role) {
      if (saved && saved.models && saved.models[role]) selection.models[role] = saved.models[role];
      if (saved && saved.reasoning && saved.reasoning[role]) selection.reasoning[role] = saved.reasoning[role];
    });
    selection.flex_mode = !!(saved && saved.flex_mode);
    return selection;
  }

  function applyProviderChange(inventory, selection, tier, providerId) {
    return selectors.applyProviderChange(
      inventory,
      templateForSelection(null),
      selection,
      providerId,
      { roles: rolesForTier(tier) }
    );
  }

  function applyModelChange(inventory, selection, role, modelId) {
    return selectors.applyRoleModelChange(inventory, selection, role, modelId);
  }

  function canSubmit(inventory, selection, tier) {
    const roles = rolesForTier(tier);
    if (!roles.length || !selectors.canSubmitBrief(
      inventory,
      selection,
      true,
      { roles: roles }
    )) return false;
    if (selection.flex_mode && !selectors.providerSupportsFlexMode(inventory, selection.provider)) {
      return false;
    }
    return true;
  }

  function buildPayload(selection, tier) {
    return selectors.buildSubmitPayload({}, selection, {
      roles: rolesForTier(tier),
      includeEmptyReasoning: true,
    });
  }

  function statusMessage(inventory) {
    const status = selectors.briefStatusMessage(inventory, true);
    if (!status.text) return status;
    return Object.assign({}, status, {
      text: status.text.replace("before creating a brief", "before changing provider"),
    });
  }

  function words(value) {
    return String(value || "").replace(/_/g, " ");
  }

  function roleLabel(role) {
    if (role === "swe") return "SWE";
    return words(role).replace(/\b\w/g, function (letter) { return letter.toUpperCase(); });
  }

  function freshnessLabel(freshness) {
    if (!freshness || freshness.stale === true || freshness.fetched_at == null) {
      return "Inventory freshness: stale or unknown";
    }
    if (typeof freshness.age_seconds === "number") {
      return "Inventory freshness: current (" + Math.max(0, Math.round(freshness.age_seconds)) + "s old)";
    }
    return "Inventory freshness: current";
  }

  function readinessSummary(readiness) {
    if (!readiness) {
      return {
        kind: "unknown",
        label: "Configuration readiness unknown",
        detail: "Provider configuration has not been evaluated.",
        freshness: "Inventory freshness: unknown",
      };
    }
    const stale = !readiness.inventory_freshness ||
      readiness.inventory_freshness.stale === true ||
      readiness.inventory_freshness.fetched_at == null;
    if (readiness.outcome === "supported") {
      return {
        kind: stale ? "unknown" : "ready",
        label: stale ? "Configuration readiness unknown · stale" : "Configuration ready",
        detail: stale
          ? "The selection passed an older observation; refresh before relying on it."
          : (readiness.message || "All configured roles are supported."),
        freshness: freshnessLabel(readiness.inventory_freshness),
      };
    }
    if (readiness.outcome === "blocked") {
      return {
        kind: "blocked",
        label: "Configuration not ready",
        detail: readiness.message || "The selected configuration is not supported.",
        freshness: freshnessLabel(readiness.inventory_freshness),
      };
    }
    return {
      kind: "unknown",
      label: stale ? "Configuration readiness unknown · stale" : "Configuration readiness unknown",
      detail: readiness.message || "Provider capability could not be confirmed.",
      freshness: freshnessLabel(readiness.inventory_freshness),
    };
  }

  function checkView(check) {
    const provider = check && check.provider ? check.provider : "not selected";
    const model = check && check.model_id ? check.model_id : "not selected";
    const reasoning = check && (check.reasoning_effective || check.reasoning_level);
    const flex = check && check.effective_flex_mode;
    const selection = provider + " / " + model +
      (reasoning ? " / reasoning " + reasoning : "") +
      (typeof flex === "boolean" ? " / Flex " + (flex ? "on" : "off") : "");
    const path = check && check.document_path ? check.document_path : "Unknown document";
    const revision = check && check.document_revision ? check.document_revision : "unknown revision";
    return {
      role: roleLabel(check && check.role) +
        (check && check.work_id ? " (" + check.work_id + ")" : ""),
      supported: !!(check && check.outcome === "supported"),
      selection: selection,
      reason: (check && check.message) || "Provider capability could not be confirmed.",
      provenance: path + " · " + revision,
    };
  }

  function diagnosticView(batch) {
    if (!batch) return null;
    return {
      summary: batch.message || "Provider configuration blocked this action.",
      action: words(batch.action || "provider action"),
      fingerprint: batch.selection_fingerprint || "unknown",
      freshness: freshnessLabel(batch.inventory_freshness),
      checks: (batch.checks || []).map(checkView),
    };
  }

  function failureBatch(payload, recovery) {
    const entries = payload && Array.isArray(payload.dispatch_refusals)
      ? payload.dispatch_refusals
      : (payload && Array.isArray(payload.preflights) ? payload.preflights : []);
    const batches = entries.filter(function (item) {
      return item && item.preflight && Array.isArray(item.preflight.checks);
    });
    if (batches.length) {
      const first = batches[0].preflight;
      return Object.assign({}, first, {
        action: batches.length > 1 ? "approval_dispatch" : first.action,
        message: (payload && payload.message) || first.message,
        selection_fingerprint: batches.length > 1 ? "multiple selections" : first.selection_fingerprint,
        checks: batches.flatMap(function (entry) {
          return entry.preflight.checks.map(function (check) {
            if (check.work_id || !entry.work_id) return check;
            return Object.assign({}, check, { work_id: entry.work_id });
          });
        }),
      });
    }
    if (payload && payload.preflight && Array.isArray(payload.preflight.checks)) {
      return payload.preflight;
    }
    if (recovery && recovery.failed_diagnostics && Array.isArray(recovery.failed_diagnostics.checks)) {
      return recovery.failed_diagnostics;
    }
    return null;
  }

  function partialOutcome(payload) {
    if (!payload || !payload.dispatch_pending) return "";
    const outcome = payload.dispatch_outcome || {};
    const launched = Array.isArray(outcome.launched) ? outcome.launched : [];
    const notLaunched = Array.isArray(outcome.not_launched) ? outcome.not_launched : [];
    const committed = payload.approval_committed
      ? "Approval was saved. "
      : "";
    return committed +
      (launched.length ? "Launched: " + launched.join(", ") + ". " : "") +
      (notLaunched.length ? "Not launched: " + notLaunched.join(", ") + "." : "Dispatch did not complete.");
  }

  return {
    TIER_ROLES: TIER_ROLES,
    rolesForTier: rolesForTier,
    initialSelection: initialSelection,
    applyProviderChange: applyProviderChange,
    applyModelChange: applyModelChange,
    canSubmit: canSubmit,
    buildPayload: buildPayload,
    statusMessage: statusMessage,
    roleLabel: roleLabel,
    freshnessLabel: freshnessLabel,
    readinessSummary: readinessSummary,
    diagnosticView: diagnosticView,
    failureBatch: failureBatch,
    partialOutcome: partialOutcome,
  };
});
