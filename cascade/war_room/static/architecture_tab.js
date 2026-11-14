(function (root, factory) {
  var api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.ArchitectureTab = api;
  if (root.document) {
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", function () { api.init(); });
    } else {
      api.init();
    }
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var LINK_KEYS = ["tab", "context", "snapshot", "view", "level", "target"];

  function linkState(search) {
    var params = new URLSearchParams(search || "");
    return {
      tab: params.get("tab") || "board",
      context: params.get("context"),
      snapshot: params.get("snapshot"),
      view: params.get("view"),
      level: params.get("level"),
      target: params.get("target"),
    };
  }

  function applyLinkState(urlValue, state) {
    var url = new URL(urlValue, "http://localhost/");
    LINK_KEYS.forEach(function (key) {
      var value = state[key];
      if (value == null || value === "" || (key === "tab" && value === "board")) {
        url.searchParams.delete(key);
      } else {
        url.searchParams.set(key, value);
      }
    });
    return url.pathname + (url.search ? url.search : "") + (url.hash || "");
  }

  function sortedChoices(target) {
    var rows = Array.isArray(target && target.drill_choices) ? target.drill_choices.slice() : [];
    var order = {
      systemLandscapeViews: 0,
      systemContextViews: 1,
      containerViews: 2,
      componentViews: 3,
      dynamicViews: 4,
      deploymentViews: 5,
      customViews: 6,
    };
    return rows.filter(function (row) {
      return row && row.view_key && row.level;
    }).sort(function (a, b) {
      var left = Object.prototype.hasOwnProperty.call(order, a.level) ? order[a.level] : 99;
      var right = Object.prototype.hasOwnProperty.call(order, b.level) ? order[b.level] : 99;
      return left - right || a.view_key.localeCompare(b.view_key) ||
        String(a.label || "").localeCompare(String(b.label || ""));
    });
  }

  function documentationContextUrl(snapshotId, view, selection) {
    var params = new URLSearchParams();
    params.set("view", view.key);
    params.set("level", view.level);
    if (selection && selection.semantic_id) {
      params.set("kind", selection.kind);
      params.set("target", selection.semantic_id);
    } else {
      params.set("kind", "view");
    }
    return "/api/architecture/snapshots/" + encodeURIComponent(snapshotId) +
      "/context?" + params.toString();
  }

  function createController(options) {
    options = options || {};
    var win = options.window || window;
    var doc = options.document || win.document;
    var request = options.fetch || win.fetch.bind(win);
    var viewerApi = options.PlanViewer || win.PlanViewer;
    var state = {
      activeTab: "board",
      catalog: null,
      catalogLoaded: false,
      context: null,
      documentationRefId: null,
      payload: null,
      view: null,
      selection: null,
      history: [],
      generation: 0,
      viewer: null,
      headTimer: null,
      pendingTimer: null,
      contextRequest: 0,
      resourceRequest: 0,
    };

    function byId(id) { return doc.getElementById(id); }
    var el = {
      app: byId("war-room-app"),
      boardTab: byId("war-room-board-tab"),
      architectureTab: byId("war-room-architecture-tab"),
      boardPanel: byId("war-room-board-panel"),
      architecturePanel: byId("war-room-architecture-panel"),
      context: byId("architecture-context"),
      invalid: byId("architecture-invalid-link"),
      documentationChoice: byId("architecture-documentation-choice"),
      documentationRef: byId("architecture-documentation-ref"),
      useDocumentationRef: byId("architecture-use-documentation-ref"),
      status: byId("architecture-status"),
      snapshot: byId("architecture-snapshot"),
      provenance: byId("architecture-provenance-list"),
      acceptedLineage: byId("architecture-accepted-lineage"),
      associatedReview: byId("architecture-associated-review"),
      updateIndicator: byId("architecture-update-indicator"),
      refreshSnapshot: byId("architecture-refresh-snapshot"),
      ready: byId("architecture-ready"),
      back: byId("architecture-back"),
      view: byId("architecture-view"),
      selectionStatus: byId("architecture-selection-status"),
      drillChoices: byId("architecture-drill-choices"),
      viewer: byId("architecture-viewer"),
      targetDetail: byId("architecture-target-detail"),
      sourceList: byId("architecture-source-list"),
      documentationContext: byId("architecture-documentation-context"),
      documentationStatus: byId("architecture-documentation-status"),
      documentationContent: byId("architecture-documentation-content"),
      documentPreview: byId("architecture-document-preview"),
      documentPreviewHeading: byId("architecture-document-preview-heading"),
      documentPreviewProvenance: byId("architecture-document-preview-provenance"),
      documentPreviewBody: byId("architecture-document-preview-body"),
      documentPreviewClose: byId("architecture-document-preview-close"),
    };

    function setStatus(message, error) {
      el.status.textContent = message || "";
      el.status.classList.toggle("error", !!error);
    }

    function showInvalid(message) {
      el.invalid.textContent = "This architecture link could not be restored: " + message;
      el.invalid.hidden = false;
    }

    function clearInvalid() {
      el.invalid.hidden = true;
      el.invalid.textContent = "";
    }

    async function json(url, init) {
      var response = await request(url, init);
      var value;
      try { value = await response.json(); } catch (_error) { value = {}; }
      if (!response.ok) {
        var error = new Error(value.error || "Request failed (HTTP " + response.status + ")");
        error.status = response.status;
        throw error;
      }
      return value;
    }

    function clearDocumentationContext(message) {
      state.contextRequest += 1;
      state.resourceRequest += 1;
      el.documentationContent.replaceChildren();
      el.documentationStatus.textContent = message || "";
      el.documentationStatus.classList.remove("error");
      el.documentPreview.hidden = true;
      el.documentPreviewBody.replaceChildren();
    }

    function sourceLabel(source) {
      if (!source) return "Source location unavailable";
      var section = source.section ? "#" + source.section : "";
      return source.repository_key + " · " + source.revision + " · " +
        source.path + section;
    }

    function addContextActions(container, resources, title, provenance) {
      var actions = doc.createElement("div");
      actions.className = "architecture-context-actions";
      [
        ["section_url", "Open source section"],
        ["document_url", "Open full document"],
      ].forEach(function (choice) {
        var url = resources && resources[choice[0]];
        if (!url) return;
        var button = doc.createElement("button");
        button.type = "button";
        button.textContent = choice[1];
        button.addEventListener("click", function () {
          openDocumentResource(url, title + " · " + choice[1], provenance);
        });
        actions.appendChild(button);
      });
      if (actions.children.length) container.appendChild(actions);
    }

    function contextState(row) {
      var badge = doc.createElement("span");
      badge.className = "architecture-context-state " + (row.state || "available");
      badge.textContent = row.state || "available";
      return badge;
    }

    function renderContextLink(row) {
      var item = doc.createElement("li");
      item.className = "architecture-context-row";
      var name = doc.createElement("strong");
      name.textContent = (row.kind === "decision" ? "Decision " : "Requirement ") +
        row.document_id + (row.title ? " — " + row.title : "");
      item.appendChild(name);
      item.appendChild(contextState(row));
      var source = doc.createElement("p");
      source.className = "architecture-context-row-meta";
      source.textContent = sourceLabel(row.source);
      item.appendChild(source);
      if (row.reason) {
        var reason = doc.createElement("p");
        reason.textContent = "Reference unavailable: " + row.reason;
        item.appendChild(reason);
      }
      var evidence = (row.provenance || []).map(function (value) {
        return value.relation + " · " + value.evidence_id;
      }).join("; ");
      if (evidence) {
        var proof = doc.createElement("p");
        proof.className = "architecture-context-row-meta";
        proof.textContent = "Evidence: " + evidence;
        item.appendChild(proof);
      }
      addContextActions(item, row.resources, row.document_id, sourceLabel(row.source));
      return item;
    }

    function renderDesignContext(row) {
      var item = doc.createElement("li");
      item.className = "architecture-context-row";
      var name = doc.createElement("strong");
      name.textContent = row.design_owner_directory === "." ?
        "Repository design" : "Design owner: " + row.design_owner_directory;
      item.appendChild(name);
      item.appendChild(contextState(row));
      var directories = doc.createElement("p");
      directories.textContent = "Code context: " + row.code_directory;
      item.appendChild(directories);
      var source = doc.createElement("p");
      source.className = "architecture-context-row-meta";
      source.textContent = sourceLabel(row.source);
      item.appendChild(source);
      if (row.reason) {
        var reason = doc.createElement("p");
        reason.textContent = "Design unavailable: " + row.reason;
        item.appendChild(reason);
      }
      addContextActions(item, { document_url: row.document_url },
        row.design_owner_directory + "/DESIGN.md", sourceLabel(row.source));
      return item;
    }

    function addContextGroup(title, description, rows, renderer, emptyMessage) {
      var section = doc.createElement("section");
      section.className = "architecture-context-group";
      var heading = doc.createElement("h4");
      heading.textContent = title;
      section.appendChild(heading);
      if (description) {
        var note = doc.createElement("p");
        note.textContent = description;
        section.appendChild(note);
      }
      if (rows && rows.length) {
        var list = doc.createElement("ul");
        list.className = "architecture-context-list";
        rows.forEach(function (row) { list.appendChild(renderer(row)); });
        section.appendChild(list);
      } else if (emptyMessage) {
        var empty = doc.createElement("p");
        empty.textContent = emptyMessage;
        section.appendChild(empty);
      }
      el.documentationContent.appendChild(section);
    }

    function renderDocumentationContext(payload, selection) {
      el.documentationContent.replaceChildren();
      var hasTarget = !!(selection && selection.semantic_id);
      var selectedLabel = hasTarget ? selection.kind + " " + selection.semantic_id :
        "view " + state.view.key;
      el.documentationStatus.textContent = "Pinned context for " + selectedLabel + ".";
      el.documentationStatus.classList.remove("error");
      if (hasTarget) {
        addContextGroup(
          "Explicit target links",
          "Only verified mappings count as coverage for this target.",
          payload.explicit_target_links || [],
          renderContextLink,
          payload.mapping_state === "unmapped" ?
            "Unmapped target — no verified explicit requirement or decision link exists." :
            "No explicit links were returned."
        );
      }
      addContextGroup(
        "View links",
        hasTarget ? "Links for the enclosing view; these do not claim target coverage." :
          "Verified requirements and decisions linked to this view.",
        payload.view_links || [],
        renderContextLink,
        "No verified requirements or decisions are linked to this view."
      );
      addContextGroup(
        "Owning designs",
        "Ownership context only; it is not an inferred requirement mapping.",
        payload.owner_context || [],
        renderDesignContext,
        "No owning design is available at the pinned documentation revision."
      );
      if (!hasTarget) {
        addContextGroup(
          "Broader design index",
          "Broader navigation for the selected view; entries are not explicit coverage.",
          payload.broader_index || [],
          renderDesignContext,
          "No broader design index entries are recorded for this snapshot."
        );
      }
    }

    async function loadDocumentationContext() {
      if (!state.payload || state.payload.state !== "ready" || !state.view) return;
      var requestId = ++state.contextRequest;
      var snapshotId = state.payload.snapshot_id;
      var view = state.view;
      var selection = state.selection && {
        kind: state.selection.kind,
        semantic_id: state.selection.semantic_id,
      };
      state.resourceRequest += 1;
      el.documentPreview.hidden = true;
      el.documentationContent.replaceChildren();
      el.documentationStatus.textContent = "Loading verified requirements and decisions…";
      el.documentationStatus.classList.remove("error");
      try {
        var payload = await json(documentationContextUrl(snapshotId, view, selection));
        if (requestId !== state.contextRequest || !state.payload ||
            state.payload.snapshot_id !== snapshotId || state.view !== view) return;
        renderDocumentationContext(payload, selection);
      } catch (error) {
        if (requestId !== state.contextRequest) return;
        el.documentationContent.replaceChildren();
        el.documentationStatus.textContent = error.message ||
          "Could not load requirements and decisions.";
        el.documentationStatus.classList.add("error");
      }
    }

    async function openDocumentResource(url, title, provenance) {
      var requestId = ++state.resourceRequest;
      el.documentPreview.hidden = false;
      el.documentPreviewHeading.textContent = title;
      el.documentPreviewProvenance.textContent = provenance;
      el.documentPreviewBody.textContent = "Loading pinned document…";
      try {
        var response = await request(url);
        if (!response.ok) throw new Error("Document request failed (HTTP " + response.status + ")");
        var body = await response.text();
        if (requestId !== state.resourceRequest) return;
        var html = viewerApi && typeof viewerApi.markdownToHtml === "function" ?
          viewerApi.markdownToHtml(body) : null;
        el.documentPreviewBody.replaceChildren();
        if (html != null) {
          el.documentPreviewBody.innerHTML = html;
        } else {
          var pre = doc.createElement("pre");
          pre.textContent = body;
          el.documentPreviewBody.appendChild(pre);
        }
      } catch (error) {
        if (requestId !== state.resourceRequest) return;
        el.documentPreviewBody.textContent = error.message || "Could not open pinned document.";
      }
    }

    function currentLink() {
      return linkState(win.location.search);
    }

    function writeLink(mode) {
      var value = {
        tab: state.activeTab,
        context: state.context && state.context.context.context_id,
        snapshot: state.payload && state.payload.snapshot_id,
        view: state.view && state.view.key,
        level: state.view && state.view.level,
        target: state.selection && state.selection.semantic_id,
      };
      var href = applyLinkState(win.location.href, value);
      win.history[mode || "replaceState"](null, "", href);
    }

    function dispatch(name, detail) {
      if (!el.app || !el.app.dispatchEvent || !win.CustomEvent) return;
      el.app.dispatchEvent(new win.CustomEvent(name, { bubbles: true, detail: detail }));
    }

    function stopHeadChecks() {
      if (state.headTimer != null) win.clearTimeout(state.headTimer);
      state.headTimer = null;
    }

    function stopPendingPoll() {
      if (state.pendingTimer != null) win.clearTimeout(state.pendingTimer);
      state.pendingTimer = null;
    }

    function scheduleHeadCheck() {
      stopHeadChecks();
      if (state.activeTab !== "architecture" || !state.payload) return;
      state.headTimer = win.setTimeout(checkHead, options.headInterval || 15000);
    }

    async function checkHead() {
      state.headTimer = null;
      if (state.activeTab !== "architecture" || !state.payload) return;
      var generation = state.generation;
      var snapshotId = state.payload.snapshot_id;
      try {
        var result = await json("/api/architecture/snapshots/" +
          encodeURIComponent(snapshotId) + "/status");
        if (generation !== state.generation || state.activeTab !== "architecture" ||
            !state.payload || state.payload.snapshot_id !== snapshotId) return;
        var changed = result.state === "changed";
        el.updateIndicator.hidden = !changed;
        el.refreshSnapshot.hidden = !changed;
      } catch (_error) {
        // Snapshot content remains useful if a background HEAD check fails.
      }
      scheduleHeadCheck();
    }

    function setTab(name, historyMode) {
      var next = name === "architecture" ? "architecture" : "board";
      state.activeTab = next;
      var architecture = next === "architecture";
      el.boardTab.setAttribute("aria-selected", String(!architecture));
      el.boardTab.tabIndex = architecture ? -1 : 0;
      el.architectureTab.setAttribute("aria-selected", String(architecture));
      el.architectureTab.tabIndex = architecture ? 0 : -1;
      el.boardPanel.hidden = architecture;
      el.architecturePanel.hidden = !architecture;
      if (historyMode) writeLink(historyMode);
      if (architecture) {
        ensureLoaded();
        if (state.payload && state.payload.state === "pending" && state.pendingTimer == null) {
          loadSnapshot(state.payload.snapshot_id, null, state.generation, false);
        }
        scheduleHeadCheck();
      } else {
        stopHeadChecks();
        stopPendingPoll();
      }
    }

    function option(select, value, label) {
      var row = doc.createElement("option");
      row.value = value;
      row.textContent = label;
      select.appendChild(row);
      return row;
    }

    function renderCatalog(catalog) {
      el.context.replaceChildren();
      catalog.contexts.forEach(function (row) {
        var context = row.context;
        var identity = context.detached ? "detached HEAD" : (context.branch || "unknown branch");
        option(el.context, context.context_id,
          context.label + " · " + identity + (context.dirty ? " · dirty" : ""));
      });
      el.context.disabled = false;
    }

    function selectedContext(contextId) {
      return state.catalog && state.catalog.contexts.find(function (row) {
        return row.context.context_id === contextId;
      });
    }

    function renderDocumentationChoice(context) {
      el.documentationChoice.hidden = false;
      el.documentationRef.replaceChildren();
      option(el.documentationRef, "", "Select a recorded documentation ref");
      (context.known_documentation_refs || []).forEach(function (row) {
        var accepted = context.accepted_lineage &&
          context.accepted_lineage.ref_id === row.ref_id ? " · accepted lineage" : "";
        option(el.documentationRef, row.ref_id,
          row.revision + " · " + row.provenance + accepted);
      });
      el.useDocumentationRef.disabled = true;
      setStatus("A documentation ref is required; tracking HEAD will not be guessed.");
    }

    function selectContext(contextId, fromLink) {
      var context = selectedContext(contextId);
      if (!context) {
        showInvalid("the selected project context is not known to this War Room session");
        return;
      }
      state.context = context;
      state.documentationRefId = null;
      el.context.value = contextId;
      el.documentationChoice.hidden = true;
      if (context.documentation_ref_required) {
        state.payload = null;
        state.view = null;
        state.selection = null;
        el.snapshot.hidden = true;
        renderDocumentationChoice(context);
        if (!fromLink) writeLink("pushState");
        return;
      }
      createSnapshot(null, fromLink ? "replaceState" : "pushState");
    }

    async function loadCatalog() {
      var catalog = await json("/api/architecture/contexts");
      state.catalog = catalog;
      state.catalogLoaded = true;
      renderCatalog(catalog);
      return catalog;
    }

    async function ensureLoaded() {
      if (state.catalogLoaded) return;
      var generation = ++state.generation;
      setStatus("Loading known architecture contexts…");
      try {
        var catalog = await loadCatalog();
        if (generation !== state.generation) return;
        var link = currentLink();
        var contextId = link.context || catalog.default_context_id;
        var context = selectedContext(contextId);
        if (!context) {
          showInvalid("context " + contextId + " is no longer available");
          setStatus("Choose one of the known project contexts to recover.", true);
          return;
        }
        state.context = context;
        el.context.value = contextId;
        if (link.snapshot) {
          loadSnapshot(link.snapshot, link, generation, true);
        } else {
          selectContext(contextId, !!link.context);
        }
      } catch (error) {
        if (generation !== state.generation) return;
        setStatus(error.message || "Could not load architecture contexts", true);
      }
    }

    async function createSnapshot(documentationRefId, historyMode) {
      if (!state.context) return;
      var generation = ++state.generation;
      stopHeadChecks();
      stopPendingPoll();
      clearInvalid();
      el.documentationChoice.hidden = true;
      setStatus("Pinning the selected revisions…");
      var body = { context_id: state.context.context.context_id };
      var chosen = documentationRefId || state.documentationRefId;
      if (chosen) body.documentation_ref_id = chosen;
      try {
        var payload = await json("/api/architecture/snapshots", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        if (generation !== state.generation) return;
        state.documentationRefId = chosen || null;
        state.history = [];
        await acceptPayload(payload, generation, null);
        if (generation !== state.generation) return;
        writeLink(historyMode || "replaceState");
      } catch (error) {
        if (generation !== state.generation) return;
        setStatus(error.message || "Could not create an architecture snapshot", true);
      }
    }

    function snapshotUrl(snapshotId, selection, cursor) {
      var params = new URLSearchParams();
      if (cursor) params.set("cursor", String(cursor));
      if (selection && selection.view && selection.level) {
        params.set("view", selection.view);
        params.set("level", selection.level);
      }
      if (selection && selection.target) params.set("target", selection.target);
      var query = params.toString();
      return "/api/architecture/snapshots/" + encodeURIComponent(snapshotId) +
        (query ? "?" + query : "");
    }

    async function loadSnapshot(snapshotId, selection, generation, linked) {
      try {
        var payload = await json(snapshotUrl(snapshotId, selection));
        if (generation !== state.generation) return;
        if (payload.context.context_id !== state.context.context.context_id) {
          throw new Error("the pinned snapshot does not belong to the selected context");
        }
        await acceptPayload(payload, generation, selection);
        if (generation !== state.generation) return;
        writeLink("replaceState");
      } catch (error) {
        if (generation !== state.generation) return;
        if (linked) showInvalid(error.message || "the snapshot is unavailable");
        setStatus(error.message || "Could not load the architecture snapshot", true);
      }
    }

    async function remainingViews(payload, generation) {
      var views = payload.views.slice();
      var cursor = payload.pagination && payload.pagination.next_cursor;
      while (cursor != null) {
        var page = await json(snapshotUrl(payload.snapshot_id, null, cursor));
        if (generation !== state.generation) return null;
        views = views.concat(page.views || []);
        cursor = page.pagination && page.pagination.next_cursor;
      }
      payload.views = views;
      if (payload.pagination) payload.pagination.next_cursor = null;
      return payload;
    }

    async function acceptPayload(payload, generation, requestedSelection) {
      if (payload.state === "ready" && payload.pagination &&
          payload.pagination.next_cursor != null) {
        payload = await remainingViews(payload, generation);
        if (!payload || generation !== state.generation) return;
      }
      state.payload = payload;
      renderSnapshot(payload, requestedSelection);
      dispatch("cascade:architecture-context", {
        context: payload.context,
        snapshot_id: payload.snapshot_id,
        provenance: payload.provenance,
      });
      if (payload.state === "pending") {
        stopPendingPoll();
        state.pendingTimer = win.setTimeout(function () {
          state.pendingTimer = null;
          if (generation === state.generation && state.activeTab === "architecture") {
            loadSnapshot(payload.snapshot_id, requestedSelection, generation, false);
          }
        }, options.pendingInterval || 1000);
      } else {
        stopPendingPoll();
        scheduleHeadCheck();
      }
    }

    function addProvenance(label, value) {
      var term = doc.createElement("dt");
      term.textContent = label;
      var detail = doc.createElement("dd");
      detail.textContent = value == null || value === "" ? "Unavailable" : String(value);
      el.provenance.appendChild(term);
      el.provenance.appendChild(detail);
    }

    function renderProvenance(payload) {
      var context = payload.context || {};
      var provenance = payload.provenance || {};
      var repositories = provenance.repositories || {};
      var revisions = provenance.revisions || {};
      var association = provenance.association || {};
      el.provenance.replaceChildren();
      addProvenance("Context", context.label);
      addProvenance("Code repository", repositories.code || context.repository_key);
      addProvenance("Branch", context.detached ? "Detached HEAD" : context.branch);
      addProvenance("Code revision", revisions.code || context.revision);
      addProvenance("Working tree", context.dirty ? "Dirty (uncommitted edits excluded)" : "Clean");
      addProvenance("Documentation repository", repositories.documentation);
      addProvenance("Documentation revision", revisions.documentation);
      addProvenance("Architecture destination", provenance.architecture_destination);
      addProvenance("Association provenance", association.provenance);
      addProvenance("Association evidence", association.evidence_id);
      var accepted = provenance.accepted_lineage;
      el.acceptedLineage.textContent = accepted ?
        "Accepted-lineage reference (separate from this branch snapshot): " +
          accepted.revision + " · " + accepted.provenance :
        "No accepted-lineage reference is recorded for this context.";
      var review = payload.associated_review;
      el.associatedReview.replaceChildren();
      el.associatedReview.hidden = !review;
      if (review) {
        el.associatedReview.appendChild(doc.createTextNode("Associated proposal: "));
        var link = doc.createElement("a");
        link.href = "/plan/" + encodeURIComponent(review.work_id);
        link.textContent = "Open " + review.work_id + " plan review";
        el.associatedReview.appendChild(link);
      }
    }

    function renderSources(resources) {
      el.sourceList.replaceChildren();
      (resources || []).forEach(function (row) {
        var item = doc.createElement("li");
        var link = doc.createElement("a");
        link.href = row.url;
        link.textContent = row.kind + ": " + row.path;
        item.appendChild(link);
        item.appendChild(doc.createTextNode(" · " + row.revision));
        el.sourceList.appendChild(item);
      });
      if (!el.sourceList.children.length) {
        var empty = doc.createElement("li");
        empty.textContent = "No model sources are available for this snapshot.";
        el.sourceList.appendChild(empty);
      }
    }

    function findView(key, level) {
      return state.payload && state.payload.views.find(function (row) {
        return row.key === key && row.level === level;
      });
    }

    function targetFor(semanticId) {
      return state.payload && state.payload.targets.find(function (row) {
        return row.semantic_id === semanticId;
      });
    }

    function viewContains(view, semanticId) {
      return !!view && (view.target_ids || []).indexOf(semanticId) !== -1;
    }

    function initialNavigation(payload, requested) {
      var selected = requested && requested.view ?
        findView(requested.view, requested.level) : null;
      if (requested && (requested.view || requested.level) && !selected) {
        showInvalid("the requested view and level are not part of this pinned snapshot");
      }
      if (!selected && payload.initial_view) {
        selected = findView(payload.initial_view.view_key, payload.initial_view.level);
      }
      selected = selected || payload.views[0] || null;
      state.view = selected;
      state.selection = null;
      if (requested && requested.target) {
        var target = targetFor(requested.target);
        if (!target || !viewContains(selected, requested.target)) {
          showInvalid("the requested semantic target is not present in the selected view");
        } else {
          state.selection = { kind: target.kind, semantic_id: target.semantic_id };
        }
      }
    }

    function renderSnapshot(payload, requestedSelection) {
      clearDocumentationContext(payload.state === "ready" ? "" :
        "Requirements and decisions are available when the snapshot is ready.");
      el.snapshot.hidden = false;
      el.updateIndicator.hidden = true;
      el.refreshSnapshot.hidden = true;
      renderProvenance(payload);
      renderSources(payload.resources);
      if (state.viewer) state.viewer.destroy();
      state.viewer = null;
      el.viewer.replaceChildren();
      el.ready.hidden = true;
      if (payload.state !== "ready") {
        var labels = {
          pending: "Rendering this pinned architecture snapshot…",
          missing_model: "No versioned architecture model exists at these pinned revisions.",
          render_failed: "The pinned architecture model could not be rendered.",
        };
        setStatus(labels[payload.state] || payload.message ||
          "Architecture is unavailable for this snapshot", payload.state !== "pending");
        return;
      }
      setStatus("Showing immutable snapshot " + payload.snapshot_id + ".");
      el.ready.hidden = false;
      initialNavigation(payload, requestedSelection);
      renderViewOptions();
      renderViewer();
    }

    function renderViewOptions() {
      el.view.replaceChildren();
      (state.payload.views || []).forEach(function (row) {
        var item = option(el.view, row.key + "\u0000" + row.level,
          row.key + " (" + row.level + ")");
        item.selected = state.view && row.key === state.view.key && row.level === state.view.level;
      });
      el.back.disabled = !viewerApi.parentViews(state.payload.views, state.view, state.payload.targets).length;
    }

    function pushNavigation() {
      state.history.push({
        view: state.view,
        selection: state.selection && {
          kind: state.selection.kind,
          semantic_id: state.selection.semantic_id,
        },
      });
    }

    function showView(view, selection, push) {
      if (!view) return;
      if (push) pushNavigation();
      state.view = view;
      state.selection = selection || null;
      el.drillChoices.hidden = true;
      renderViewOptions();
      renderViewer();
      writeLink("pushState");
    }

    function renderTargetDetail(target) {
      el.targetDetail.replaceChildren();
      el.targetDetail.hidden = !target;
      if (!target) return;
      var heading = doc.createElement("h3");
      heading.textContent = target.kind === "relationship" ? "Relationship" : "Element";
      var label = doc.createElement("p");
      label.textContent = target.label || target.semantic_id;
      var identity = doc.createElement("p");
      var code = doc.createElement("code");
      code.textContent = target.semantic_id;
      identity.appendChild(code);
      el.targetDetail.appendChild(heading);
      el.targetDetail.appendChild(label);
      el.targetDetail.appendChild(identity);
      if (target.kind === "relationship") {
        var endpoints = doc.createElement("p");
        endpoints.textContent = (target.source || "?") + " → " + (target.destination || "?");
        el.targetDetail.appendChild(endpoints);
      }
    }

    function chooseDrill(target, choices) {
      el.drillChoices.replaceChildren();
      var note = doc.createElement("p");
      note.textContent = "Choose a verified drill destination for " +
        (target.label || target.semantic_id) + ".";
      el.drillChoices.appendChild(note);
      choices.forEach(function (choice) {
        var button = doc.createElement("button");
        button.type = "button";
        button.textContent = choice.label || choice.view_key + " (" + choice.level + ")";
        button.addEventListener("click", function () {
          showView(findView(choice.view_key, choice.level), null, true);
        });
        el.drillChoices.appendChild(button);
      });
      el.drillChoices.hidden = false;
    }

    function renderViewer() {
      if (state.viewer) state.viewer.destroy();
      state.viewer = null;
      el.viewer.replaceChildren();
      var view = state.view;
      if (!view) {
        el.selectionStatus.textContent = "No architecture views are present.";
        return;
      }
      var targets = (state.payload.targets || []).filter(function (row) {
        return viewContains(view, row.semantic_id);
      }).map(function (row) {
        return Object.assign({ state: "unchanged" }, row);
      });
      var selectedTarget = state.selection && targetFor(state.selection.semantic_id);
      el.selectionStatus.textContent = selectedTarget ?
        selectedTarget.kind + ": " + (selectedTarget.label || selectedTarget.semantic_id) :
        "Select an element or relationship for details.";
      renderTargetDetail(selectedTarget);
      if (!viewerApi || typeof viewerApi.createSemanticC4Viewer !== "function") {
        setStatus("The shared semantic architecture viewer is unavailable.", true);
        return;
      }
      state.viewer = viewerApi.createSemanticC4Viewer({
        document: doc,
        container: el.viewer,
        sideName: "branch",
        view: view,
        side: { svg: view.artifact_url, targets: targets },
        selection: state.selection && {
          kind: state.selection.kind,
          semantic_id: state.selection.semantic_id,
          source_side: "branch",
        },
        status: el.selectionStatus,
        onSelect: function (detail) {
          pushNavigation();
          state.selection = { kind: detail.kind, semantic_id: detail.semantic_id };
          renderViewOptions();
          renderViewer();
          writeLink("pushState");
          dispatch("cascade:architecture-selection", {
            context: state.payload.context,
            snapshot_id: state.payload.snapshot_id,
            view_key: state.view.key,
            level: state.view.level,
            kind: detail.kind,
            semantic_id: detail.semantic_id,
          });
        },
        onDrill: function (detail) {
          var choices = (detail.choices || sortedChoices(detail.target)).filter(function (choice) {
            return !!findView(choice.view_key, choice.level);
          });
          if (choices.length === 1) {
            showView(findView(choices[0].view_key, choices[0].level), null, true);
          } else if (choices.length > 1) {
            chooseDrill(detail.target, choices);
          }
        },
      });
      loadDocumentationContext();
    }

    function handlePopState() {
      var link = currentLink();
      setTab(link.tab, null);
      if (link.tab !== "architecture" || !state.catalogLoaded) return;
      var contextId = link.context || state.catalog.default_context_id;
      var context = selectedContext(contextId);
      if (!context) {
        showInvalid("context " + contextId + " is no longer available");
        return;
      }
      state.context = context;
      el.context.value = contextId;
      var generation = ++state.generation;
      if (link.snapshot) loadSnapshot(link.snapshot, link, generation, true);
      else selectContext(contextId, true);
    }

    function install() {
      el.boardTab.addEventListener("click", function () { setTab("board", "pushState"); });
      el.architectureTab.addEventListener("click", function () {
        setTab("architecture", "pushState");
      });
      [el.boardTab, el.architectureTab].forEach(function (tab, index, tabs) {
        tab.addEventListener("keydown", function (event) {
          var next = null;
          if (event.key === "ArrowRight" || event.key === "ArrowLeft") next = tabs[index ? 0 : 1];
          if (event.key === "Home") next = tabs[0];
          if (event.key === "End") next = tabs[tabs.length - 1];
          if (!next) return;
          event.preventDefault();
          next.focus();
          next.click();
        });
      });
      el.context.addEventListener("change", function () {
        clearInvalid();
        selectContext(el.context.value, false);
      });
      el.documentationRef.addEventListener("change", function () {
        el.useDocumentationRef.disabled = !el.documentationRef.value;
      });
      el.useDocumentationRef.addEventListener("click", function () {
        if (el.documentationRef.value) createSnapshot(el.documentationRef.value, "pushState");
      });
      el.refreshSnapshot.addEventListener("click", function () {
        var association = state.payload && state.payload.provenance &&
          state.payload.provenance.association;
        var ref = association && association.provenance === "user_selected" ?
          association.evidence_id : state.documentationRefId;
        createSnapshot(ref || null, "pushState");
      });
      el.view.addEventListener("change", function () {
        var parts = el.view.value.split("\u0000");
        showView(findView(parts[0], parts[1]), null, true);
      });
      el.back.addEventListener("click", function () {
        var parents = viewerApi.parentViews(state.payload.views, state.view, state.payload.targets);
        if (parents.length === 1) showView(parents[0], null, true);
        else if (parents.length > 1) chooseDrill({ label: "parent view" }, parents.map(function (view) {
          return { view_key: view.key, level: view.level, label: view.key };
        }));
      });
      el.documentPreviewClose.addEventListener("click", function () {
        state.resourceRequest += 1;
        el.documentPreview.hidden = true;
        el.documentPreviewBody.replaceChildren();
      });
      win.addEventListener("popstate", handlePopState);
      var initial = currentLink();
      if (initial.tab !== "board" && initial.tab !== "architecture") {
        showInvalid("unknown tab " + initial.tab);
        initial.tab = "board";
      }
      setTab(initial.tab, null);
    }

    return {
      install: install,
      setTab: setTab,
      state: state,
    };
  }

  function init(options) {
    var doc = options && options.document || (typeof document !== "undefined" ? document : null);
    if (!doc || !doc.getElementById("war-room-architecture-tab")) return null;
    var controller = createController(options);
    controller.install();
    return controller;
  }

  return {
    applyLinkState: applyLinkState,
    createController: createController,
    documentationContextUrl: documentationContextUrl,
    init: init,
    linkState: linkState,
    sortedChoices: sortedChoices,
  };
});
