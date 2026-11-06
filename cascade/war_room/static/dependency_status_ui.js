(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.DependencyStatusUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const BOARD_COLUMNS = ["1_backlog", "2_active", "3_completed"];

  function findRoomItem(view, graphId) {
    if (!view || !graphId) return null;
    const tier = graphId.indexOf("feat_") === 0 ? "features" : "epics";
    const rows = view[tier] || {};
    for (let i = 0; i < BOARD_COLUMNS.length; i += 1) {
      const items = rows[BOARD_COLUMNS[i]] || [];
      for (let j = 0; j < items.length; j += 1) {
        if (items[j].id === graphId) return items[j];
      }
    }
    return null;
  }

  function observedLabel(value) {
    return value ? "Observed at " + String(value) : "Observation time unavailable";
  }

  function renderCurrentSummary(document, host, projection) {
    if (!host) return null;
    host.replaceChildren();
    host.hidden = !projection;
    if (!projection) return null;

    const heading = document.createElement("h3");
    heading.textContent = "Current dependency status";
    host.appendChild(heading);

    const outcome = document.createElement("p");
    outcome.className = "dependency-current-outcome dependency-outcome-" +
      String(projection.outcome || "unknown");
    outcome.textContent = projection.explanation || String(projection.outcome || "Unknown");
    host.appendChild(outcome);

    const rows = projection.dependencies || [];
    if (rows.length) {
      const list = document.createElement("ul");
      list.className = "dependency-current-list";
      rows.forEach(function (row) {
        const item = document.createElement("li");
        item.textContent = String(row.work_id || "Dependency") + ": " +
          String(row.explanation || row.outcome || "Unknown");
        list.appendChild(item);
      });
      host.appendChild(list);
    }

    const observed = document.createElement("time");
    observed.className = "dependency-observed-at";
    if (projection.observed_at) observed.setAttribute("datetime", projection.observed_at);
    observed.textContent = observedLabel(projection.observed_at);
    host.appendChild(observed);
    return host;
  }

  function appendHistoricalObservation(document, messageElement, message) {
    const meta = document.createElement("div");
    meta.className = "chat-observed-at";
    const prefix = "Historical transcript · ";
    if (message && message.ts) {
      const time = document.createElement("time");
      time.setAttribute("datetime", message.ts);
      time.textContent = prefix + observedLabel(message.ts);
      meta.appendChild(time);
    } else {
      meta.textContent = prefix + "observation time unavailable";
    }
    messageElement.appendChild(meta);
    return meta;
  }

  return {
    findRoomItem: findRoomItem,
    renderCurrentSummary: renderCurrentSummary,
    appendHistoricalObservation: appendHistoricalObservation,
  };
});
