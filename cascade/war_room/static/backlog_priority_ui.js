(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.BacklogPriorityUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function copyProjection(value) {
    if (!value || !Array.isArray(value.feature_ids) || typeof value.token !== "string") {
      return null;
    }
    return { feature_ids: value.feature_ids.slice(), token: value.token };
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
    return next;
  }

  function isActionTarget(target) {
    return !!(
      target && target.closest &&
      target.closest("button, a, input, select, textarea, [role='button'], .board-row-actions")
    );
  }

  function createController(deps) {
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
      const projections = (view && view.backlog_feature_priorities) || {};
      Object.keys(projections).forEach(function (epicId) {
        const projection = copyProjection(projections[epicId]);
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
        if (row && projectionFor(row.parent)) {
          (positions[row.parent] || (positions[row.parent] = [])).push(index);
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
        const response = await apiPost("/api/reorder_backlog_features", {
          epic_id: epicId,
          feature_ids: featureIds,
          expected_token: current.token,
        });
        const accepted = copyProjection(response.body);
        if (accepted) {
          markSuperseded(epicId, current.token);
          confirmed[epicId] = accepted;
        }
        delete pending[epicId];
        if (focus) requestFocus(focus.featureId, focus.control);
        rerender();
        setStatus("Backlog priority updated for " + epicId + ".", false);
        return true;
      } catch (err) {
        const body = err && err.body;
        const currentProjection = copyProjection(body);
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
      const projection = projectionFor(item.parent);
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
          spec.label + " " + item.id + " in " + item.parent + " backlog priority"
        );
        button.disabled = spec.boundary;
        if (pending[item.parent]) {
          button.setAttribute("aria-disabled", "true");
          button.title = "Saving backlog priority";
        }
        button.addEventListener("click", function (event) {
          event.preventDefault();
          event.stopPropagation();
          if (button.disabled || pending[item.parent]) return;
          const latest = projectionFor(item.parent);
          const next = latest && moveFeature(latest.feature_ids, item.id, spec.offset);
          if (next) submit(item.parent, next, { featureId: item.id, control: spec.direction });
        });
        actions.appendChild(button);
      });
    }

    function decorateRow(row, item) {
      const projection = projectionFor(item.parent);
      if (!projection || projection.feature_ids.indexOf(item.id) < 0) return;
      row.draggable = !pending[item.parent];
      row.dataset.backlogPriorityEpic = item.parent;
      row.setAttribute("aria-roledescription", "Draggable backlog feature");
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
        if (pending[item.parent] || isActionTarget(event.target)) {
          event.preventDefault();
          return;
        }
        dragged = { featureId: item.id, epicId: item.parent };
        row.classList.add("board-row-dragging");
        if (event.dataTransfer) {
          event.dataTransfer.effectAllowed = "move";
          event.dataTransfer.setData("text/plain", item.id);
        }
      });
      row.addEventListener("dragover", function (event) {
        if (!dragged || dragged.epicId !== item.parent || dragged.featureId === item.id) return;
        event.preventDefault();
        if (event.dataTransfer) event.dataTransfer.dropEffect = "move";
      });
      row.addEventListener("drop", function (event) {
        if (!dragged || dragged.epicId !== item.parent || dragged.featureId === item.id) return;
        event.preventDefault();
        event.stopPropagation();
        const latest = projectionFor(item.parent);
        const rect = row.getBoundingClientRect ? row.getBoundingClientRect() : null;
        const after = !!(rect && typeof event.clientY === "number" && event.clientY > rect.top + rect.height / 2);
        const next = latest && dropFeature(latest.feature_ids, dragged.featureId, item.id, after);
        const movedId = dragged.featureId;
        dragged = null;
        if (next) submit(item.parent, next, null);
      });
      row.addEventListener("dragend", function () {
        dragged = null;
        row.classList.remove("board-row-dragging");
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
    };
  }

  return {
    createController: createController,
    moveFeature: moveFeature,
    dropFeature: dropFeature,
    isActionTarget: isActionTarget,
  };
});
