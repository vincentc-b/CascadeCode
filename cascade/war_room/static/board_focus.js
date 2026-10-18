(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.BoardFocus = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const BOARD_COLUMNS = ["1_backlog", "2_active", "3_completed"];

  function defaultBoardFocus() {
    return {
      selected_epic_id: null,
      selected_feature_id: null,
      completed_collapsed: {
        epics: false,
        features: true,
        tasks: true,
      },
    };
  }

  function copyFocusFields(focus) {
    const collapsed = focus.completed_collapsed || {};
    return {
      selected_epic_id: focus.selected_epic_id != null ? focus.selected_epic_id : null,
      selected_feature_id:
        focus.selected_feature_id != null ? focus.selected_feature_id : null,
      completed_collapsed: Object.assign({}, collapsed),
    };
  }

  function toggleCompletedCollapsed(focus, tier) {
    const next = copyFocusFields(focus);
    next.completed_collapsed[tier] = !next.completed_collapsed[tier];
    return next;
  }

  function activeEpicIds(view) {
    if (!view || !view.epics) return [];
    const items = view.epics["2_active"];
    if (!Array.isArray(items)) return [];
    return items.map(function (item) {
      return item.id;
    });
  }

  function featureParentIds(view, focus) {
    if (focus && focus.selected_epic_id != null) {
      return [focus.selected_epic_id];
    }
    return activeEpicIds(view);
  }

  function isFeaturesLensEmpty(view, focus) {
    return featureParentIds(view, focus).length === 0;
  }

  function findFeatureItem(view, featureId) {
    if (!view || !view.features || featureId == null) return null;
    for (let i = 0; i < BOARD_COLUMNS.length; i += 1) {
      const col = BOARD_COLUMNS[i];
      const items = view.features[col] || [];
      for (let j = 0; j < items.length; j += 1) {
        if (items[j].id === featureId) {
          return items[j];
        }
      }
    }
    return null;
  }

  function findFeatureParent(view, featureId) {
    const item = findFeatureItem(view, featureId);
    return item && item.parent != null ? item.parent : null;
  }

  function filterFeaturesTier(featuresTier, parentSet) {
    const filtered = {};
    BOARD_COLUMNS.forEach(function (col) {
      const items = (featuresTier && featuresTier[col]) || [];
      filtered[col] = items.filter(function (item) {
        return parentSet.has(item.parent);
      });
    });
    return filtered;
  }

  function emptyFeaturesTier() {
    return {
      "1_backlog": [],
      "2_active": [],
      "3_completed": [],
    };
  }

  function emptyTasksTier() {
    return {
      "1_backlog": [],
      "2_active": [],
      "3_completed": [],
    };
  }

  function filterTasksTier(tasksTier, featureId) {
    const filtered = {};
    BOARD_COLUMNS.forEach(function (col) {
      const items = (tasksTier && tasksTier[col]) || [];
      filtered[col] = items.filter(function (item) {
        return item.parent === featureId;
      });
    });
    return filtered;
  }

  function applyEpicLens(view, focus) {
    if (!view) return view;
    if (isFeaturesLensEmpty(view, focus)) {
      return {
        epics: view.epics,
        features: emptyFeaturesTier(),
        tasks: view.tasks,
      };
    }
    const parents = featureParentIds(view, focus);
    const parentSet = new Set(parents);
    return {
      epics: view.epics,
      features: filterFeaturesTier(view.features, parentSet),
      tasks: view.tasks,
    };
  }

  function isTasksLensEmpty(focus) {
    return !focus || focus.selected_feature_id == null;
  }

  function applyFeatureLens(view, focus) {
    if (!view) return view;
    if (isTasksLensEmpty(focus)) {
      return {
        epics: view.epics,
        features: view.features,
        tasks: emptyTasksTier(),
      };
    }
    return {
      epics: view.epics,
      features: view.features,
      tasks: filterTasksTier(view.tasks, focus.selected_feature_id),
    };
  }

  function isSelectedFeatureInEpicLens(view, focus) {
    if (!focus || focus.selected_feature_id == null) return true;
    const epicView = applyEpicLens(view, focus);
    return findFeatureItem(epicView, focus.selected_feature_id) != null;
  }

  function reconcileFocusWithLens(view, focus) {
    if (!view || !focus || focus.selected_feature_id == null) return focus;
    if (isSelectedFeatureInEpicLens(view, focus)) return focus;
    const next = copyFocusFields(focus);
    next.selected_feature_id = null;
    return next;
  }

  function applyBoardLens(view, focus) {
    const epicView = applyEpicLens(view, focus);
    if (focus && focus.selected_feature_id != null && !findFeatureItem(epicView, focus.selected_feature_id)) {
      return {
        epics: epicView.epics,
        features: epicView.features,
        tasks: emptyTasksTier(),
      };
    }
    return applyFeatureLens(epicView, focus);
  }

  function applyFeatureSelection(focus, featureItem) {
    const next = copyFocusFields(focus);
    next.selected_feature_id = featureItem.id;
    next.selected_epic_id = featureItem.parent != null ? featureItem.parent : null;
    return next;
  }

  function toggleFeatureSelection(focus, featureId, view) {
    const next = copyFocusFields(focus);
    if (next.selected_feature_id === featureId) {
      next.selected_feature_id = null;
      return next;
    }
    const item = findFeatureItem(view, featureId);
    if (!item) return next;
    return applyFeatureSelection(next, item);
  }

  function toggleEpicSelection(focus, epicId, view) {
    const next = copyFocusFields(focus);
    if (next.selected_epic_id === epicId) {
      next.selected_epic_id = null;
      if (next.selected_feature_id != null) {
        const parentSet = new Set(featureParentIds(view, next));
        const featureParent = findFeatureParent(view, next.selected_feature_id);
        if (featureParent == null || !parentSet.has(featureParent)) {
          next.selected_feature_id = null;
        }
      }
      return next;
    }
    next.selected_epic_id = epicId;
    if (next.selected_feature_id != null) {
      const featureParent = findFeatureParent(view, next.selected_feature_id);
      if (featureParent !== epicId) {
        next.selected_feature_id = null;
      }
    }
    return next;
  }

  function countVisibleInColumn(visibleView, tier, column) {
    if (!visibleView || !visibleView[tier]) return 0;
    const items = visibleView[tier][column];
    return Array.isArray(items) ? items.length : 0;
  }

  return {
    defaultBoardFocus: defaultBoardFocus,
    toggleCompletedCollapsed: toggleCompletedCollapsed,
    countVisibleInColumn: countVisibleInColumn,
    activeEpicIds: activeEpicIds,
    featureParentIds: featureParentIds,
    isFeaturesLensEmpty: isFeaturesLensEmpty,
    isTasksLensEmpty: isTasksLensEmpty,
    applyEpicLens: applyEpicLens,
    applyFeatureLens: applyFeatureLens,
    applyBoardLens: applyBoardLens,
    reconcileFocusWithLens: reconcileFocusWithLens,
    isSelectedFeatureInEpicLens: isSelectedFeatureInEpicLens,
    toggleEpicSelection: toggleEpicSelection,
    toggleFeatureSelection: toggleFeatureSelection,
    applyFeatureSelection: applyFeatureSelection,
    findFeatureItem: findFeatureItem,
    findFeatureParent: findFeatureParent,
  };
});
