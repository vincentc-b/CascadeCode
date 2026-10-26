(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.BriefDefaultsUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const BRIEF_STACK_ROLES = [
    "epic_manager",
    "epic_architect",
    "feature_lead",
    "feature_architect",
    "swe",
  ];

  const ROLE_LABELS = {
    epic_manager: "Epic Manager model",
    epic_architect: "Epic Architect model",
    feature_lead: "Feature Lead model",
    feature_architect: "Feature Architect model",
    swe: "SWE model",
  };

  function providerById(inventory, providerId) {
    if (!inventory || !inventory.providers || !providerId) return null;
    for (let i = 0; i < inventory.providers.length; i += 1) {
      if (inventory.providers[i].id === providerId) return inventory.providers[i];
    }
    return null;
  }

  function providerSupportsFlexMode(inventory, providerId) {
    const provider = providerById(inventory, providerId);
    return !!(provider && provider.supports_flex_mode);
  }

  function normalizeFlexMode(inventory, providerId, value, defaultEnabled) {
    if (!providerSupportsFlexMode(inventory, providerId)) return false;
    return typeof value === "boolean" ? value : !!defaultEnabled;
  }

  function renderFlexModeControl(wrap, checkbox, inventory, selection) {
    if (!selection) return;
    const supported = providerSupportsFlexMode(inventory, selection.provider);
    selection.flex_mode = normalizeFlexMode(
      inventory,
      selection.provider,
      selection.flex_mode,
      false
    );
    if (wrap) wrap.hidden = !supported;
    if (!checkbox) return;
    checkbox.disabled = !supported;
    checkbox.checked = selection.flex_mode;
    checkbox.onchange = supported
      ? function () {
          selection.flex_mode = checkbox.checked;
        }
      : null;
  }

  function modelById(provider, modelId) {
    if (!provider || !provider.models || !modelId) return null;
    for (let i = 0; i < provider.models.length; i += 1) {
      if (provider.models[i].id === modelId) return provider.models[i];
    }
    return null;
  }

  function reasoningChoices(model) {
    if (!model || !model.reasoning) return null;
    const capability = model.reasoning;
    if (capability.default_only) return null;
    const levels = [capability.default_level].concat(capability.override_levels || []);
    const seen = {};
    const choices = [{ value: "", label: "Provider default" }];
    levels.forEach(function (level) {
      if (!level || seen[level]) return;
      seen[level] = true;
      choices.push({ value: level, label: level });
    });
    return choices;
  }

  function roleFallbackFromTemplate(template, providerId, role) {
    if (!template) return "";
    const saved = template.saved;
    if (saved && saved.provider === providerId && saved.models && saved.models[role]) {
      return saved.models[role];
    }
    const providerDefaults = (template.provider_models || {})[providerId] || {};
    if (providerDefaults[role]) return providerDefaults[role];
    const models = template.models || {};
    return models[role] || "";
  }

  function resolveProviderId(inventory, template, preserveSaved) {
    const saved = template && template.saved;
    if (saved && saved.provider && (preserveSaved || providerById(inventory, saved.provider))) {
      return saved.provider;
    }
    if (template && template.provider && providerById(inventory, template.provider)) {
      return template.provider;
    }
    if (inventory && inventory.default_provider && providerById(inventory, inventory.default_provider)) {
      return inventory.default_provider;
    }
    if (inventory && inventory.providers && inventory.providers[0]) {
      return inventory.providers[0].id;
    }
    return "";
  }

  function revalidateRoleModel(inventory, providerId, role, currentModelId, fallbackModelId, preserveSaved) {
    const provider = providerById(inventory, providerId);
    if (!provider) return preserveSaved ? currentModelId : "";
    const resolvedFallback = fallbackModelId || roleFallbackFromTemplate(null, providerId, role);
    if (currentModelId && (preserveSaved || modelById(provider, currentModelId))) return currentModelId;
    if (resolvedFallback && modelById(provider, resolvedFallback)) return resolvedFallback;
    return provider.models[0] ? provider.models[0].id : "";
  }

  function revalidateReasoningForRole(inventory, providerId, role, modelId, currentReasoning) {
    const provider = providerById(inventory, providerId);
    const model = provider ? modelById(provider, modelId) : null;
    let choices = reasoningChoices(model);
    if (!choices) return "";
    if (!currentReasoning) return "";
    for (let i = 0; i < choices.length; i += 1) {
      if (choices[i].value === currentReasoning) return currentReasoning;
    }
    return "";
  }

  function initialSelection(inventory, template, options) {
    options = options || {};
    const preserveSaved = !!options.preserveSaved;
    const providerId = resolveProviderId(inventory, template, preserveSaved);
    const models = {};
    const reasoning = {};
    BRIEF_STACK_ROLES.forEach(function (role) {
      const savedReasoning =
        template && template.saved && template.saved.reasoning
          ? template.saved.reasoning[role] || ""
          : "";
      const fallback = roleFallbackFromTemplate(template, providerId, role);
      models[role] = revalidateRoleModel(inventory, providerId, role, fallback, fallback, preserveSaved);
      reasoning[role] = preserveSaved && savedReasoning ? savedReasoning : revalidateReasoningForRole(
        inventory, providerId, role, models[role], savedReasoning
      );
    });
    const saved = template && template.saved;
    const flexMode = normalizeFlexMode(
      inventory,
      providerId,
      saved ? saved.flex_mode : undefined,
      true
    );
    return { provider: providerId, models: models, reasoning: reasoning, flex_mode: flexMode };
  }

  function applyProviderChange(inventory, template, selection, nextProviderId) {
    const models = {};
    const reasoning = {};
    BRIEF_STACK_ROLES.forEach(function (role) {
      const fallback = roleFallbackFromTemplate(template, nextProviderId, role);
      models[role] = revalidateRoleModel(
        inventory,
        nextProviderId,
        role,
        selection.models[role],
        fallback
      );
      reasoning[role] = revalidateReasoningForRole(
        inventory,
        nextProviderId,
        role,
        models[role],
        selection.reasoning[role]
      );
    });
    return {
      provider: nextProviderId,
      models: models,
      reasoning: reasoning,
      flex_mode: normalizeFlexMode(inventory, nextProviderId, selection.flex_mode, false),
    };
  }

  function applyRoleModelChange(inventory, selection, role, nextModelId) {
    const models = Object.assign({}, selection.models);
    const reasoning = Object.assign({}, selection.reasoning);
    models[role] = revalidateRoleModel(
      inventory,
      selection.provider,
      role,
      nextModelId,
      nextModelId
    );
    reasoning[role] = revalidateReasoningForRole(
      inventory,
      selection.provider,
      role,
      models[role],
      selection.reasoning[role]
    );
    return {
      provider: selection.provider,
      models: models,
      reasoning: reasoning,
      flex_mode: selection.flex_mode,
    };
  }

  function canSubmitBrief(inventory, selection, trackingReady, options) {
    options = options || {};
    if (trackingReady === false) return false;
    if (!inventory || inventory.loading) return false;
    if (!inventory.providers || !inventory.providers.length) return false;
    const provider = providerById(inventory, selection.provider);
    const saved = options.savedSelection || null;
    if (!provider) return !!options.allowSavedUnavailable && saved && selection.provider === saved.provider && JSON.stringify(selection.models) === JSON.stringify(saved.models);
    for (let i = 0; i < BRIEF_STACK_ROLES.length; i += 1) {
      const role = BRIEF_STACK_ROLES[i];
      const modelId = selection.models[role];
      if (!modelId || (!modelById(provider, modelId) && !(options.allowSavedUnavailable && saved && saved.models[role] === modelId))) return false;
      const reasoning = selection.reasoning[role];
      if (reasoning) {
        const choices = reasoningChoices(modelById(provider, modelId));
        if (!choices || !choices.some(function (choice) { return choice.value === reasoning; })) {
          return false;
        }
      }
    }
    return true;
  }

  function buildSubmitPayload(formFields, selection, options) {
    options = options || {};
    const payload = Object.assign({}, formFields, {
      provider: selection.provider,
      models: Object.assign({}, selection.models),
      flex_mode: !!selection.flex_mode,
    });
    const reasoning = {};
    BRIEF_STACK_ROLES.forEach(function (role) {
      if (selection.reasoning[role]) reasoning[role] = selection.reasoning[role];
    });
    if (Object.keys(reasoning).length || options.includeEmptyReasoning) payload.reasoning = reasoning;
    return payload;
  }

  function buildEditSubmitPayload(formFields, selection, target) {
    const payload = buildSubmitPayload(formFields, selection, { includeEmptyReasoning: true });
    payload.epic_id = target.epic_id;
    payload.source_path = target.source_path;
    payload.source_revision = target.source_revision;
    return payload;
  }

  function briefStatusMessage(inventory, trackingReady) {
    if (!inventory || inventory.loading) {
      return {
        text: "Loading available providers and models…",
        error: false,
        recoverable: false,
      };
    }
    if (inventory.refresh && inventory.refresh.failed) {
      return {
        text:
          "Could not refresh model inventory. Retry below or check provider settings.",
        error: true,
        recoverable: true,
      };
    }
    if (!inventory.providers || !inventory.providers.length) {
      return {
        text:
          "No usable provider is available. Install and authenticate a provider CLI or save a token under Providers.",
        error: true,
        recoverable: true,
      };
    }
    if (trackingReady === false) {
      return {
        text:
          "Install and authenticate gh or glab for this origin before creating a brief.",
        error: false,
        recoverable: false,
      };
    }
    return { text: "", error: false, recoverable: false };
  }

  function renderRoleSelectors(container, inventory, template, selection, handlers, options) {
    options = options || {};
    if (!container) return;
    container.replaceChildren();
    const provider = providerById(inventory, selection.provider);
    BRIEF_STACK_ROLES.forEach(function (role) {
      const wrap = document.createElement("div");
      wrap.className = "brief-role-row";

      const modelLabel = document.createElement("label");
      modelLabel.textContent = ROLE_LABELS[role] || role;
      const modelSelect = document.createElement("select");
      modelSelect.dataset.role = role;
      modelSelect.dataset.kind = "model";
      modelSelect.required = true;
      modelSelect.disabled = !provider;
      (provider ? provider.models : []).forEach(function (model) {
        const option = document.createElement("option");
        option.value = model.id;
        option.textContent = model.display_name || model.id;
        option.selected = model.id === selection.models[role];
        modelSelect.appendChild(option);
      });
      if (options.preserveUnavailable && selection.models[role] && !modelById(provider, selection.models[role])) {
        const unavailable = document.createElement("option");
        unavailable.value = selection.models[role];
        unavailable.textContent = selection.models[role] + " (saved; unavailable)";
        unavailable.selected = true;
        modelSelect.appendChild(unavailable);
      }
      modelLabel.appendChild(modelSelect);

      const suggestion = document.createElement("small");
      suggestion.className = "brief-role-suggestion";
      const hints = (template && template.suggestions) || {};
      suggestion.textContent = hints[role] || "";

      wrap.appendChild(modelLabel);
      wrap.appendChild(suggestion);

      const model = provider ? modelById(provider, selection.models[role]) : null;
      let choices = reasoningChoices(model);
      if (!choices && options.preserveUnavailable && selection.reasoning[role]) {
        choices = [{ value: selection.reasoning[role], label: selection.reasoning[role] + " (saved)" }, { value: "", label: "Provider default (clear override)" }];
      }
      if (choices) {
        const reasoningLabel = document.createElement("label");
        reasoningLabel.textContent = "Reasoning";
        const reasoningSelect = document.createElement("select");
        reasoningSelect.dataset.role = role;
        reasoningSelect.dataset.kind = "reasoning";
        choices.forEach(function (choice) {
          const option = document.createElement("option");
          option.value = choice.value;
          option.textContent = choice.label;
          option.selected = choice.value === (selection.reasoning[role] || "");
          reasoningSelect.appendChild(option);
        });
        reasoningLabel.appendChild(reasoningSelect);
        wrap.appendChild(reasoningLabel);
      }

      if (handlers && typeof handlers.onChange === "function") {
        modelSelect.addEventListener("change", function () {
          handlers.onChange(role, "model", modelSelect.value);
        });
        const reasoningSelect = wrap.querySelector('select[data-kind="reasoning"]');
        if (reasoningSelect) {
          reasoningSelect.addEventListener("change", function () {
            handlers.onChange(role, "reasoning", reasoningSelect.value);
          });
        }
      }

      container.appendChild(wrap);
    });
  }

  return {
    BRIEF_STACK_ROLES: BRIEF_STACK_ROLES,
    ROLE_LABELS: ROLE_LABELS,
    providerById: providerById,
    providerSupportsFlexMode: providerSupportsFlexMode,
    normalizeFlexMode: normalizeFlexMode,
    renderFlexModeControl: renderFlexModeControl,
    modelById: modelById,
    reasoningChoices: reasoningChoices,
    resolveProviderId: resolveProviderId,
    initialSelection: initialSelection,
    applyProviderChange: applyProviderChange,
    applyRoleModelChange: applyRoleModelChange,
    canSubmitBrief: canSubmitBrief,
    buildSubmitPayload: buildSubmitPayload,
    buildEditSubmitPayload: buildEditSubmitPayload,
    briefStatusMessage: briefStatusMessage,
    renderRoleSelectors: renderRoleSelectors,
  };
});
