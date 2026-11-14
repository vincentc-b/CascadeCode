(function (root, factory) {
  var api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.DependencyReviewUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  var BINDING_LABELS = {
    dependency_id: "Dependency ID",
    version: "Exact version",
    source: "Authoritative source",
    digest: "Checksum / digest",
    target_environment: "Target environment",
    install_scope: "Install scope",
    install_destination: "Destination",
    operation: "Exact operation",
    cleanup_plan: "Cleanup plan",
  };
  var pingRequestIds = {};

  function appendText(document, parent, tag, className, text) {
    var node = document.createElement(tag);
    node.className = className || "";
    node.textContent = text == null || text === "" ? "Unknown" : String(text);
    parent.appendChild(node);
    return node;
  }

  function displayValue(value) {
    if (value == null || value === "") return "Unknown";
    if (Array.isArray(value)) return value.length ? value.join(", ") : "None";
    if (typeof value === "object") {
      return Object.keys(value)
        .map(function (key) { return key + "=" + String(value[key] == null ? "unknown" : value[key]); })
        .join(" · ");
    }
    return String(value);
  }

  function appendField(document, list, label, value, options) {
    var wrap = document.createElement("div");
    wrap.className = "dependency-review-field";
    appendText(document, wrap, "dt", "dependency-review-field-label", label);
    var dd = document.createElement("dd");
    dd.className = "dependency-review-field-value";
    var valueNode = dd;
    if (options && options.pre) {
      valueNode = appendText(
        document,
        dd,
        "pre",
        "dependency-review-output",
        displayValue(value)
      );
    } else {
      dd.textContent = displayValue(value);
    }
    if (options && options.code) valueNode.classList.add("dependency-review-code");
    wrap.appendChild(dd);
    list.appendChild(wrap);
    return valueNode;
  }

  function stateLabel(state) {
    return String(state || "unknown").replace(/_/g, " ");
  }

  function approvalReference(row) {
    var approval = row && row.installation_approval;
    var current = approval && Array.isArray(approval.current) ? approval.current : [];
    return current.length && current[current.length - 1].approval_id
      ? current[current.length - 1].approval_id
      : null;
  }

  function approvalReferences(projection) {
    var references = {};
    (projection.dependencies || []).forEach(function (row) {
      var reference = approvalReference(row);
      if (reference) references[row.dependency_id] = reference;
    });
    return references;
  }

  function requestId(epicId, projection) {
    var revision = projection.manifest && projection.manifest.revision;
    var key = "cascade-dependency-ping:" + epicId + ":" + String(revision || "none");
    if (pingRequestIds[key]) return pingRequestIds[key];
    try {
      var saved = globalThis.sessionStorage && globalThis.sessionStorage.getItem(key);
      if (saved) {
        pingRequestIds[key] = saved;
        return saved;
      }
    } catch (_err) {
      /* Stable storage is an enhancement; the id remains stable for this panel. */
    }
    var suffix;
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
      suffix = globalThis.crypto.randomUUID();
    } else {
      suffix = String(Date.now()) + "-" + String(Math.random()).slice(2);
    }
    var value = "dependency-ping-" + epicId + "-" + suffix;
    pingRequestIds[key] = value;
    try {
      if (globalThis.sessionStorage) globalThis.sessionStorage.setItem(key, value);
    } catch (_err2) {
      /* See above. */
    }
    return value;
  }

  function defaultPost(path, payload) {
    return fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (response) {
      return response.text().then(function (raw) {
        var body;
        try { body = JSON.parse(raw); } catch (_err) { body = { error: raw }; }
        if (!response.ok) {
          var refusal = body && body.refusal;
          var error = new Error(
            (refusal && refusal.detail) || body.error || response.statusText || "Action refused"
          );
          error.body = body;
          error.status = response.status;
          throw error;
        }
        return body;
      });
    });
  }

  function appendBootstrap(document, body, projection, runAction) {
    var bootstrap = projection.bootstrap;
    // Ordinary dependency bounds are derived automatically, not another human gate.
    if (!bootstrap || !bootstrap.scope || !(bootstrap.scope.feasibility_artifacts || []).length) return;
    var section = document.createElement("section");
    section.className = "dependency-review-bootstrap";
    appendText(document, section, "h4", "dependency-review-subheading", "Bootstrap review");
    var fields = document.createElement("dl");
    fields.className = "dependency-review-fields";
    appendField(document, fields, "State", stateLabel(bootstrap.state));
    appendField(document, fields, "Responsible actor", projection.responsible_actor || "None");
    appendField(document, fields, "Scope revision", bootstrap.revision);
    appendField(document, fields, "Manifest revision in scope", bootstrap.scope_manifest_revision);
    appendField(document, fields, "Scope current", bootstrap.scope_current === true ? "Yes" : "No");
    appendField(document, fields, "Feasibility authorization", stateLabel(bootstrap.authorization_state));
    section.appendChild(fields);

    if (bootstrap.scope) {
      var scopeDetails = document.createElement("details");
      scopeDetails.className = "dependency-review-scope";
      appendText(document, scopeDetails, "summary", "dependency-review-detail-summary", "Reviewed narrow feasibility scope");
      appendText(
        document,
        scopeDetails,
        "pre",
        "dependency-review-output",
        JSON.stringify(bootstrap.scope, null, 2)
      );
      section.appendChild(scopeDetails);
    }
    (bootstrap.projection_blockers || []).forEach(function (blocker) {
      appendText(document, section, "p", "dependency-review-warning", blocker);
    });

    if (
      bootstrap.scope && bootstrap.scope_current === true &&
      bootstrap.authorization_state !== "current" &&
      bootstrap.authorization_state !== "not_required"
    ) {
      var review = appendText(document, section, "button", "dependency-review-action", "Review bootstrap scope");
      review.type = "button";
      review.addEventListener("click", function () {
        runAction(review, "Reviewing bootstrap scope…", "/api/review_dependency_bootstrap", {
          epic_id: projection.epic_id,
          bootstrap_revision: bootstrap.revision,
          scope_fingerprint: bootstrap.scope_fingerprint,
          scope: bootstrap.scope,
        });
      });
    }
    body.appendChild(section);
  }

  function appendBinding(document, parent, binding) {
    var list = document.createElement("dl");
    list.className = "dependency-review-fields dependency-review-binding";
    Object.keys(BINDING_LABELS).forEach(function (key) {
      appendField(document, list, BINDING_LABELS[key], binding && binding[key], {
        code: key === "operation" || key === "cleanup_plan",
      });
    });
    parent.appendChild(list);
  }

  function appendDependency(document, list, row, selected) {
    var card = document.createElement("article");
    card.className = "dependency-review-entry dependency-review-entry-" + String(row.status || "blocked");
    var heading = document.createElement("div");
    heading.className = "dependency-review-entry-heading";
    appendText(document, heading, "h4", "dependency-review-subheading", row.dependency_id);
    var approvalState = row.installation_approval && row.installation_approval.state;
    appendText(
      document,
      heading,
      "span",
      "dependency-review-badge dependency-review-approval-" + String(approvalState || "missing"),
      "Installation approval: " + (row.status === "ready" && approvalState !== "current"
        ? "not needed (already verified)" : stateLabel(approvalState))
    );
    card.appendChild(heading);

    if (approvalState !== "current" && row.status !== "ready") {
      var choice = document.createElement("label");
      choice.className = "dependency-review-select";
      var checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.checked = true;
      checkbox.value = row.dependency_id;
      checkbox.addEventListener("change", function () {
        if (checkbox.checked) selected[row.dependency_id] = row.binding;
        else delete selected[row.dependency_id];
      });
      selected[row.dependency_id] = row.binding;
      choice.appendChild(checkbox);
      appendText(document, choice, "span", "", "Include in installation approval");
      card.appendChild(choice);
    }

    appendBinding(document, card, row.binding || {});
    var context = document.createElement("dl");
    context.className = "dependency-review-fields";
    appendField(document, context, "Why needed", row.why_needed);
    appendField(document, context, "Responsible actor", row.responsible_actor || "None");
    appendField(document, context, "Actual environment", row.actual_environment);
    appendField(
      document,
      context,
      "Environment matches target",
      row.environment_matches_target == null ? "Not checked" : row.environment_matches_target ? "Yes" : "No"
    );
    if (row.last_check) {
      appendField(document, context, "Last attempt", row.last_check.completed_at || row.last_check.admitted_at);
      appendField(document, context, "Last operation", row.last_check.operation, { code: true });
      appendField(document, context, "Last result", stateLabel(row.last_check.result));
      appendField(document, context, "Redacted output", row.last_check.redacted_output, { pre: true });
    } else {
      appendField(document, context, "Last attempt", "Never checked");
    }
    var evidence = row.evidence || {};
    appendField(document, context, "Failure", evidence.failure || "None", { pre: true });
    appendField(document, context, "Next safe action", evidence.next_action || "No next action recorded");
    var guidance = row.guidance || {};
    appendField(document, context, "Investigation", guidance.investigation || "Unknown — investigate before acting", { code: true });
    appendField(document, context, "Safe setup", guidance.setup || "Unknown — no install command is available", { code: true });
    appendField(document, context, "Verification operation", guidance.verification_operation, { code: true });
    appendField(document, context, "Expected verification", guidance.expected_verification);
    appendField(document, context, "Owned-artifact cleanup", guidance.owned_artifact_cleanup, { code: true });
    card.appendChild(context);

    var approvals = row.installation_approval || {};
    (approvals.current || []).forEach(function (approval) {
      appendText(
        document,
        card,
        "p",
        "dependency-review-approval-reference",
        "Current approval " + approval.approval_id + " by " + approval.approver_id + " at " + approval.approved_at
      );
    });
    if ((approvals.stale || []).length) {
      appendText(
        document,
        card,
        "p",
        "dependency-review-warning",
        String(approvals.stale.length) + " stale approval record(s); the displayed binding needs fresh approval."
      );
    }
    list.appendChild(card);
  }

  function renderInto(document, host, projection, options) {
    options = options || {};
    var declarationPending = (projection.errors || []).some(function (error) {
      return error.code === "missing_manifest";
    });
    var statusLabel = declarationPending ? "Awaiting Epic Team declaration" : stateLabel(projection.status);
    host.replaceChildren();
    host.className = "dependency-review-panel dependency-review-status-" + String(projection.status || "blocked");
    host.setAttribute("role", "region");
    host.setAttribute("aria-label", "Software dependency review for " + projection.epic_id);

    var heading = document.createElement("div");
    heading.className = "dependency-review-heading";
    appendText(document, heading, "h3", "dependency-review-title", "Dependency bootstrap");
    appendText(
      document,
      heading,
      "span",
      "dependency-review-badge",
      statusLabel
    );
    host.appendChild(heading);

    var feedback = appendText(document, host, "p", "dependency-review-feedback", "");
    feedback.setAttribute("role", "status");
    feedback.hidden = true;

    var body = document.createElement("div");
    body.className = "dependency-review-body";
    host.appendChild(body);

    var overview = document.createElement("dl");
    overview.className = "dependency-review-fields dependency-review-overview";
    appendField(document, overview, "Verification status", statusLabel);
    appendField(document, overview, "Responsible actor", projection.responsible_actor || "None");
    appendField(
      document,
      overview,
      "Manifest revision",
      projection.manifest && projection.manifest.revision
    );
    appendField(
      document,
      overview,
      "Required environment",
      projection.manifest && projection.manifest.target_environment
    );
    appendField(
      document,
      overview,
      "Declared actual environment",
      projection.manifest && projection.manifest.declared_actual_environment
    );
    body.appendChild(overview);

    if (projection.explicit_no_dependencies) {
      appendText(
        document,
        body,
        "p",
        "dependency-review-ready",
        "No software dependencies are required. Dependency readiness is ready."
      );
      if (projection.planning_readiness) {
        appendText(
          document,
          body,
          "p",
          "dependency-review-planning",
          "Planning readiness: " + stateLabel(projection.planning_readiness.status)
        );
      }
      return { host: host, feedback: feedback, projection: projection };
    }

    (projection.errors || []).forEach(function (error) {
      appendText(document, body, "p", "dependency-review-warning", error.code === "missing_manifest" ? "Waiting for the Epic Team to declare software prerequisites. Plan approval remains unavailable until declaration and verification are complete." : error.code + ": " + error.detail);
    });

    if ((projection.errors || []).some(function (error) { return error.code === "missing_manifest"; })) {
      appendText(document, body, "p", "dependency-review-guidance",
        "The Epic Manager or Architect must declare dependencies first. Ask the team to use read_dependency_manifest and write_dependency_manifest. If none are needed, declare none_required with a complete target environment. Installation approval remains a separate human action.");
      return { host: host, feedback: feedback, projection: projection };
    }

    var post = options.post || defaultPost;
    function applyProjection(next) {
      projection = next || projection;
      if (typeof options.onProjection === "function") options.onProjection(projection);
      return renderInto(document, host, projection, options);
    }
    function runAction(button, pending, path, payload) {
      button.disabled = true;
      feedback.hidden = false;
      feedback.classList.remove("dependency-review-feedback-error");
      feedback.textContent = pending;
      return Promise.resolve(post(path, payload)).then(function (result) {
        var bodyResult = result && result.body ? result.body : result;
        var next = bodyResult && bodyResult.dependency_status;
        var rendered = next ? applyProjection(next) : { feedback: feedback };
        rendered.feedback.hidden = false;
        var continuation = bodyResult && (bodyResult.continuation || bodyResult.ping);
        rendered.feedback.textContent = continuation
          ? (continuation.ready ? "Dependencies verified. Planning can continue."
            : continuation.next_action || "Verification is still blocked. Review the failure details below; installation approval is separate from verification.")
          : "Dependency state refreshed.";
        return bodyResult;
      }).catch(function (error) {
        var errorBody = error && error.body;
        var next = errorBody && errorBody.dependency_status;
        var rendered = next ? applyProjection(next) : { feedback: feedback };
        var refusal = errorBody && errorBody.refusal;
        rendered.feedback.hidden = false;
        rendered.feedback.classList.add("dependency-review-feedback-error");
        rendered.feedback.textContent =
          (refusal && refusal.detail) || (error && error.message) || "Action refused";
        if (!next) button.disabled = false;
        return null;
      });
    }

    appendBootstrap(document, body, projection, runAction);

    var selected = {};
    var dependencies = document.createElement("div");
    dependencies.className = "dependency-review-entries";
    (projection.dependencies || []).forEach(function (row) {
      appendDependency(document, dependencies, row, selected);
    });
    body.appendChild(dependencies);

    var controls = document.createElement("div");
    controls.className = "dependency-review-controls";
    var approvable = (projection.dependencies || []).some(function (row) {
      return row.status !== "ready" && (!row.installation_approval || row.installation_approval.state !== "current");
    });
    if (approvable && projection.manifest) {
      var approve = appendText(document, controls, "button", "dependency-review-action", "Approve selected installations");
      approve.type = "button";
      approve.addEventListener("click", function () {
        var entries = Object.keys(selected).map(function (dependencyId) {
          return { dependency_id: dependencyId, binding: selected[dependencyId] };
        });
        if (!entries.length) {
          feedback.hidden = false;
          feedback.classList.add("dependency-review-feedback-error");
          feedback.textContent = "Select at least one dependency binding to approve.";
          return;
        }
        runAction(approve, "Approving installation and verifying dependencies…", "/api/approve_dependency_installations", {
          epic_id: projection.epic_id,
          manifest_revision: projection.manifest.revision,
          entries: entries,
        });
      });
    }

    var pingId = requestId(projection.epic_id, projection);
    appendText(document, controls, "p", "dependency-review-guidance", "Existing installations are verified automatically. Human approval permits only the displayed installation; verification and planning continuation then run automatically.");
    var ping = appendText(document, controls, "button", "dependency-review-action", "Retry verification");
    ping.type = "button";
    ping.addEventListener("click", function () {
      runAction(ping, "Requesting a same-run dependency recheck…", "/api/ping_dependency_team", {
        epic_id: projection.epic_id,
        request_id: pingId,
        approval_references: approvalReferences(projection),
      });
    });
    body.appendChild(controls);

    if (projection.planning_readiness) {
      var planning = projection.planning_readiness;
      appendText(
        document,
        body,
        "p",
        planning.can_approve_plan ? "dependency-review-planning" : "dependency-review-warning",
        "Planning readiness: " + stateLabel(planning.status) +
          (planning.approve_disabled_reason ? " — " + stateLabel(planning.approve_disabled_reason) : "")
      );
    }
    return { host: host, feedback: feedback, projection: projection };
  }

  function appendPanel(document, parent, projection, options) {
    if (!projection) return null;
    var host = document.createElement("section");
    parent.appendChild(host);
    host.addEventListener("click", function (event) {
      if (event && typeof event.stopPropagation === "function") event.stopPropagation();
    });
    return renderInto(document, host, projection, options);
  }

  return {
    BINDING_LABELS: BINDING_LABELS,
    approvalReferences: approvalReferences,
    displayValue: displayValue,
    renderInto: renderInto,
    appendPanel: appendPanel,
  };
});
