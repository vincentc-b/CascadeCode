(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.BacklogPriorityUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function copyProjection(value, idField) {
    const field = idField || "feature_ids";
    if (!value || !Array.isArray(value[field]) || typeof value.token !== "string") {
      return null;
    }
    return { feature_ids: value[field].slice(), token: value.token };
  }

  function moveFeature(featureIds, featureId, offset) {
    const next = featureIds.slice();
    const from = next.indexOf(featureId);
    const to = from + offset;
    if (from < 0 || to < 0 || to >= next.length) return null;
    next.splice(from, 1);
    next.splice(to, 0, featureId);
    return next;
  }

  function dropFeature(featureIds, featureId, targetId, afterTarget) {
    if (featureId === targetId) return null;
    const next = featureIds.filter(function (id) { return id !== featureId; });
    const targetIndex = next.indexOf(targetId);
    if (targetIndex < 0 || next.length === featureIds.length) return null;
    next.splice(targetIndex + (afterTarget ? 1 : 0), 0, featureId);
    return next.every(function (id, index) { return id === featureIds[index]; }) ? null : next;
  }

  function isActionTarget(target) {
    return !!(
      target && target.closest &&
      target.closest("button, a, input, select, textarea, [role='button'], .board-row-actions")
    );
  }

  function createController(deps) {
    const epicScope = deps.scope === "epic";
    const idField = epicScope ? "epic_ids" : "feature_ids";
    const groupFor = epicScope
      ? function () { return "backlog_epics"; }
      : function (item) { return item.parent; };
    const document = deps.document;
    const apiPost = deps.apiPost;
    const setStatus = deps.setStatus;
    const rerender = deps.rerender;
    const confirmed = Object.create(null);
    const pending = Object.create(null);
    const supersededTokens = Object.create(null);
    let dragged = null;
    let focusRequest = null;

    function syncBoard(view) {
      const projections = epicScope
        ? ((view && view.backlog_epic_priority)
          ? { backlog_epics: view.backlog_epic_priority } : {})
        : ((view && view.backlog_feature_priorities) || {});
      Object.keys(projections).forEach(function (epicId) {
        const projection = copyProjection(projections[epicId], idField);
        if (
          !projection ||
          (supersededTokens[epicId] && supersededTokens[epicId].has(projection.token))
        ) return;
        confirmed[epicId] = projection;
      });
      Object.keys(confirmed).forEach(function (epicId) {
        if (!Object.prototype.hasOwnProperty.call(projections, epicId) && !pending[epicId]) {
          delete confirmed[epicId];
        }
      });
    }

    function projectionFor(epicId) {
      return pending[epicId] || confirmed[epicId] || null;
    }

    function orderRows(rows) {
      const ordered = rows.slice();
      const positions = Object.create(null);
      ordered.forEach(function (row, index) {
        const group = row && groupFor(row);
        if (group && projectionFor(group)) {
          (positions[group] || (positions[group] = [])).push(index);
        }
      });
      Object.keys(positions).forEach(function (epicId) {
        const indexes = positions[epicId];
        const byId = Object.create(null);
        indexes.forEach(function (index) { byId[ordered[index].id] = ordered[index]; });
        const peers = projectionFor(epicId).feature_ids
          .map(function (id) { return byId[id]; })
          .filter(Boolean);
        indexes.forEach(function (index, peerIndex) {
          if (peers[peerIndex]) ordered[index] = peers[peerIndex];
        });
      });
      return ordered;
    }

    function requestFocus(featureId, control) {
      focusRequest = { featureId: featureId, control: control };
    }

    function markSuperseded(epicId, token) {
      if (!supersededTokens[epicId]) supersededTokens[epicId] = new Set();
      supersededTokens[epicId].add(token);
    }

    function restoreFocus() {
      if (!focusRequest || !deps.board) return;
      const selector = '[data-id="' + focusRequest.featureId + '"] ' +
        '[data-backlog-move="' + focusRequest.control + '"]';
      let control = deps.board.querySelector(selector);
      if (control && control.disabled) {
        const fallback = focusRequest.control === "up" ? "down" : "up";
        control = deps.board.querySelector(
          '[data-id="' + focusRequest.featureId + '"] ' +
          '[data-backlog-move="' + fallback + '"]'
        );
      }
      if (control && control.focus) control.focus();
      focusRequest = null;
    }

    async function submit(epicId, featureIds, focus) {
      const current = confirmed[epicId];
      if (!current || pending[epicId]) return false;
      pending[epicId] = { feature_ids: featureIds.slice(), token: current.token };
      if (focus) requestFocus(focus.featureId, focus.control);
      rerender();
      try {
        const payload = { expected_token: current.token };
        payload[idField] = featureIds;
        if (!epicScope) payload.epic_id = epicId;
        const response = await apiPost(
          epicScope ? "/api/reorder_backlog_epics" : "/api/reorder_backlog_features",
          payload
        );
        const accepted = copyProjection(response.body, idField);
        if (accepted) {
          markSuperseded(epicId, current.token);
          confirmed[epicId] = accepted;
        }
        delete pending[epicId];
        if (focus) requestFocus(focus.featureId, focus.control);
        rerender();
        setStatus(epicScope ? "Backlog epic order updated." : "Backlog priority updated for " + epicId + ".", false);
        return true;
      } catch (err) {
        const body = err && err.body;
        const currentProjection = copyProjection(body, idField);
        if (currentProjection) {
          markSuperseded(epicId, current.token);
          confirmed[epicId] = currentProjection;
        }
        delete pending[epicId];
        if (focus) requestFocus(focus.featureId, focus.control);
        rerender();
        const stale = body && body.code === "stale_priority";
        const message = stale
          ? "Backlog priority changed elsewhere. Restored the current server order; try again."
          : "Could not update backlog priority. Restored the last server-confirmed order. " +
            ((body && body.error) || (err && err.message) || "Request failed");
        setStatus(message, true);
        return false;
      }
    }

    function appendMoveControls(actions, item) {
      const group = groupFor(item);
      const projection = projectionFor(group);
      if (!projection) return;
      const index = projection.feature_ids.indexOf(item.id);
      if (index < 0) return;
      [
        { direction: "up", label: "Move up", offset: -1, boundary: index === 0 },
        {
          direction: "down",
          label: "Move down",
          offset: 1,
          boundary: index === projection.feature_ids.length - 1,
        },
      ].forEach(function (spec) {
        const button = document.createElement("button");
        button.type = "button";
        button.textContent = spec.label;
        button.dataset.backlogMove = spec.direction;
        button.setAttribute(
          "aria-label",
          spec.label + " " + item.id + " in " + (epicScope ? "epic" : item.parent) + " backlog priority"
        );
        button.disabled = spec.boundary;
        if (pending[group]) {
          button.setAttribute("aria-disabled", "true");
          button.title = "Saving backlog priority";
        }
        button.addEventListener("click", function (event) {
          event.preventDefault();
          event.stopPropagation();
          if (button.disabled || pending[group]) return;
          const latest = projectionFor(group);
          const next = latest && moveFeature(latest.feature_ids, item.id, spec.offset);
          if (next) submit(group, next, { featureId: item.id, control: spec.direction });
        });
        actions.appendChild(button);
      });
    }

    function decorateRow(row, item) {
      const group = groupFor(item);
      const projection = projectionFor(group);
      if (!projection || projection.feature_ids.indexOf(item.id) < 0) return;
      const dragHint = document.createElement("span");
      dragHint.className = "backlog-drag-hint";
      dragHint.textContent = pending[group] ? "Saving priority…" : "⋮⋮ Drag to reorder";
      dragHint.title = epicScope ? "Drag this epic within the backlog" : "Drag this feature within the " + item.parent + " backlog";
      row.insertBefore(dragHint, row.firstChild);
      row.draggable = !pending[group];
      row.dataset.backlogPriorityEpic = group;
      row.setAttribute("aria-roledescription", epicScope ? "Draggable backlog epic" : "Draggable backlog feature");
      let suppressClickUntil = 0;
      row.addEventListener("click", function (event) {
        if (Date.now() > suppressClickUntil) return;
        suppressClickUntil = 0;
        event.preventDefault();
        event.stopPropagation();
        if (event.stopImmediatePropagation) event.stopImmediatePropagation();
      }, true);
      row.addEventListener("dragstart", function (event) {
        suppressClickUntil = Date.now() + 500;
        if (pending[group] || isActionTarget(event.target)) {
          event.preventDefault();
          return;
        }
        dragged = { featureId: item.id, epicId: group };
        row.classList.add("board-row-dragging");
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", item.id);
        }
      });
      row.addEventListener("dragover", function (event) {
        if (!dragged || dragged.epicId !== group || dragged.featureId === item.id) return;
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
      });
      row.addEventListener("drop", function (event) {
        if (!dragged || dragged.epicId !== group || dragged.featureId === item.id) return;
        event.preventDefault();
        event.stopPropagation();
        const latest = projectionFor(group);
        const rect = row.getBoundingClientRect ? row.getBoundingClientRect() : null;
        const after = !!(rect && typeof event.clientY === "number" && event.clientY > rect.top + rect.height / 2);
        const next = latest && dropFeature(latest.feature_ids, dragged.featureId, item.id, after);
        const movedId = dragged.featureId;
        dragged = null;
        if (next) submit(group, next, null);
      });
      row.addEventListener("dragend", function () {
        const wasDragging = !!dragged;
        dragged = null;
        row.classList.remove("board-row-dragging");
        if (wasDragging) rerender();
      });
    }

    return {
      syncBoard: syncBoard,
      orderRows: orderRows,
      appendMoveControls: appendMoveControls,
      decorateRow: decorateRow,
      restoreFocus: restoreFocus,
      submit: submit,
      projectionFor: projectionFor,
      isDragging: function () { return !!dragged; },
    };
  }

  return {
    createController: createController,
    moveFeature: moveFeature,
    dropFeature: dropFeature,
    isActionTarget: isActionTarget,
  };
});
