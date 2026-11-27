(function (root, factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  root.OpenReviewsPane = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function actionLink(label, href) {
    const link = document.createElement("a");
    link.className = "board-action-link";
    link.href = href;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.textContent = label;
    if (typeof link.addEventListener === "function") {
      link.addEventListener("click", function (ev) {
        ev.stopPropagation();
      });
    }
    return link;
  }

  function reviewStateLabel(state) {
    if (state === "awaiting_review") return "Awaiting review";
    if (state === "preparing_review") return "Preparing review";
    return state || "Unknown";
  }

  function evidenceSummary(review) {
    const evidence = review.evidence || {};
    const ci = evidence.ci || {};
    const feedback = evidence.feedback || {};
    return "CI: " + (evidence.health_state || "unknown") +
      " · policy: " + (ci.policy_status || "unknown") +
      " · feedback: " + (feedback.approval_state || feedback.status || "unknown") +
      " · freshness: " + (evidence.freshness || "unknown");
  }

  function actionResultLabel(result) {
    if (!result) return "";
    const state = result.verified ? "Verified" :
      result.executing ? "Executing" :
      result.admitted ? "Admitted" :
      result.refused ? "Refused" :
      result.waiting ? "Waiting" : "Requested";
    const next = result.next_prerequisite || result.next_action || result.blocker;
    return state + (next ? " · Next: " + next : "");
  }

  function repairIdentityComplete(review) {
    const identity = review.repair_identity || {};
    return ["review_url", "review_forge", "source_ref", "target_ref",
      "observed_source_head", "observed_target_head"].every(function (field) {
        return typeof identity[field] === "string" && identity[field].length > 0;
      }) && Number.isInteger(identity.observed_review_generation) &&
      identity.observed_review_generation >= 0;
  }

  function renderOpenReviewCard(review, options) {
    options = options || {};
    const li = document.createElement("li");
    li.className = "open-review-card";
    li.dataset.reviewId = review.id || "";

    const title = document.createElement("h3");
    title.className = "open-review-feature-title";
    const ctx = review.context || {};
    title.textContent = ctx.feature_title || review.id || "Feature";
    li.appendChild(title);

    const meta = document.createElement("p");
    meta.className = "open-review-context";
    const epicLabel = ctx.epic_title || ctx.epic_id || "—";
    const featureId = ctx.feature_id || review.id || "";
    meta.textContent =
      (featureId ? featureId + " · " : "") + "Epic: " + epicLabel;
    li.appendChild(meta);

    const state = document.createElement("p");
    state.className = "open-review-state";
    state.textContent = reviewStateLabel(review.state);
    li.appendChild(state);

    const lifecycle = document.createElement("p");
    lifecycle.className = "open-review-lifecycle";
    lifecycle.textContent = "Implementation: " +
      (review.implementation_complete ? "complete" : (review.implementation_status || "unknown")) +
      " · Delivery: " + (review.delivery_status || "unknown") +
      " · Repair generation: " + String((review.repair && review.repair.generation) || 0);
    li.appendChild(lifecycle);

    const health = document.createElement("p");
    health.className = "open-review-evidence";
    health.textContent = evidenceSummary(review);
    li.appendChild(health);

    const prerequisite = document.createElement("p");
    prerequisite.className = "open-review-prerequisite";
    prerequisite.textContent = "Next: " + (review.next_prerequisite || "unknown");
    li.appendChild(prerequisite);

    if (review.url) {
      li.appendChild(actionLink("Open review", review.url));
    } else {
      const missing = document.createElement("p");
      missing.className = "open-review-missing-url";
      missing.textContent = "Review URL unavailable.";
      li.appendChild(missing);
    }

    const form = document.createElement("form");
    form.className = "open-review-repair-form";
    const requestId = document.createElement("input");
    requestId.name = "request_id";
    requestId.required = true;
    requestId.maxLength = 160;
    requestId.placeholder = "Stable request ID";
    requestId.setAttribute("aria-label", "Stable repair request ID for " + (review.id || "Feature"));
    const reason = document.createElement("input");
    reason.name = "reason";
    reason.required = true;
    reason.maxLength = 500;
    reason.placeholder = "Repair reason";
    reason.setAttribute("aria-label", "Repair reason for " + (review.id || "Feature"));
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.textContent = "Request repair";
    submit.disabled = !repairIdentityComplete(review) || typeof options.onRepair !== "function";
    form.appendChild(requestId);
    form.appendChild(reason);
    form.appendChild(submit);
    const actionStatus = document.createElement("p");
    actionStatus.className = "open-review-repair-result";
    actionStatus.setAttribute("role", "status");
    actionStatus.setAttribute("aria-live", "polite");
    actionStatus.textContent = actionResultLabel(options.actionResult);
    form.appendChild(actionStatus);
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (submit.disabled) return;
      submit.disabled = true;
      submit.textContent = "Requesting…";
      actionStatus.textContent = "Submitting authenticated repair request…";
      options.onRepair(review, {
        request_id: requestId.value.trim(),
        reason: reason.value.trim(),
      }).catch(function (error) {
        if (!li.isConnected) return;
        actionStatus.textContent = error.message || "Repair request failed";
        actionStatus.classList.add("error");
        submit.disabled = false;
        submit.textContent = "Request repair";
      });
    });
    li.appendChild(form);

    return li;
  }

  function renderOpenReviews(data, listEl, options) {
    if (!listEl) return;
    listEl.innerHTML = "";
    const reviews = (data && data.reviews) || [];
    if (!reviews.length) {
      const empty = document.createElement("li");
      empty.className = "open-reviews-empty";
      empty.textContent = "No open merge requests.";
      listEl.appendChild(empty);
      return;
    }
    reviews.forEach(function (review) {
      listEl.appendChild(renderOpenReviewCard(review, {
        onRepair: options && options.onRepair,
        actionResult: options && options.actionResults && options.actionResults[review.id],
      }));
    });
  }

  function createOpenReviewsPane(config) {
    const paneEl = (config && config.elements) || {};
    const apiGet = config && config.apiGet;
    const apiPost = config && config.apiPost;
    let openReviewsLoadInFlight = false;
    let refreshAgain = false;
    let responseToken = 0;
    let lastData = null;
    const actionTokens = {};
    const actionResults = {};

    function setOpenReviewsStatus(msg, isError) {
      const statusEl = paneEl.openReviewsStatus;
      if (!statusEl) return;
      statusEl.textContent = msg || "";
      statusEl.classList.toggle("error", !!isError);
    }

    async function refreshOpenReviews(options) {
      if (!paneEl.openReviewsList) return;
      if (typeof apiGet !== "function") return;
      const userInitiated = !options || options.userInitiated !== false;
      if (openReviewsLoadInFlight) {
        refreshAgain = true;
        return;
      }
      const token = ++responseToken;
      openReviewsLoadInFlight = true;
      if (userInitiated && paneEl.btnRefreshOpenReviews) {
        paneEl.btnRefreshOpenReviews.disabled = true;
      }
      if (userInitiated) {
        setOpenReviewsStatus("Loading…", false);
      }
      try {
        const data = await apiGet("/api/open-reviews");
        if (token !== responseToken) return;
        lastData = data;
        renderOpenReviews(data, paneEl.openReviewsList, {
          onRepair: submitRepair,
          actionResults: actionResults,
        });
        const count = ((data && data.reviews) || []).length;
        setOpenReviewsStatus(
          count === 1 ? "1 open merge request." : count + " open merge requests.",
          false
        );
      } catch (err) {
        if (paneEl.openReviewsList) {
          paneEl.openReviewsList.innerHTML = "";
        }
        setOpenReviewsStatus(err.message || "Failed to load open reviews", true);
      } finally {
        openReviewsLoadInFlight = false;
        if (paneEl.btnRefreshOpenReviews) {
          paneEl.btnRefreshOpenReviews.disabled = false;
        }
        if (refreshAgain) {
          refreshAgain = false;
          refreshOpenReviews({ userInitiated: false }).catch(function (error) {
            setOpenReviewsStatus(error.message || "Refresh failed", true);
          });
        }
      }
    }

    async function submitRepair(review, input) {
      if (typeof apiPost !== "function") return;
      const identity = review.repair_identity || {};
      const featureId = review.accountable_feature_id || review.id;
      const token = (actionTokens[featureId] || 0) + 1;
      actionTokens[featureId] = token;
      responseToken += 1; // A GET started before this action cannot overwrite its result.
      const payload = Object.assign({}, identity, {
        feature_id: featureId,
        request_id: input.request_id,
        reason: input.reason,
        evidence: {
          source: "war_room",
          review_health: review.evidence || {},
        },
        approval_reference: "authenticated-human:" + featureId,
        scope_reference: "open-review:" + identity.review_url,
      });
      const response = await apiPost("/api/open-reviews/repair", payload);
      if (actionTokens[featureId] !== token) return;
      actionResults[featureId] = response && response.body ? response.body : response;
      if (lastData) {
        renderOpenReviews(lastData, paneEl.openReviewsList, {
          onRepair: submitRepair,
          actionResults: actionResults,
        });
      }
      await refreshOpenReviews({ userInitiated: false });
    }

    return {
      setOpenReviewsStatus,
      refreshOpenReviews,
      renderOpenReviews,
      renderOpenReviewCard,
      reviewStateLabel,
      submitRepair,
    };
  }

  return {
    createOpenReviewsPane,
    renderOpenReviews,
    renderOpenReviewCard,
    reviewStateLabel,
  };
});
