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

  return {
    TIER_ROLES: TIER_ROLES,
    rolesForTier: rolesForTier,
    initialSelection: initialSelection,
    applyProviderChange: applyProviderChange,
    applyModelChange: applyModelChange,
    canSubmit: canSubmit,
    buildPayload: buildPayload,
    statusMessage: statusMessage,
  };
});
