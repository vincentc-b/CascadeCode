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

  function renderOpenReviewCard(review) {
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

    if (review.url) {
      li.appendChild(actionLink("Open review", review.url));
    } else {
      const missing = document.createElement("p");
      missing.className = "open-review-missing-url";
      missing.textContent = "Review URL unavailable.";
      li.appendChild(missing);
    }

    return li;
  }

  function renderOpenReviews(data, listEl) {
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
      listEl.appendChild(renderOpenReviewCard(review));
    });
  }

  function createOpenReviewsPane(config) {
    const paneEl = (config && config.elements) || {};
    const apiGet = config && config.apiGet;
    let openReviewsLoadInFlight = false;

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
      if (openReviewsLoadInFlight) return;
      openReviewsLoadInFlight = true;
      if (userInitiated && paneEl.btnRefreshOpenReviews) {
        paneEl.btnRefreshOpenReviews.disabled = true;
      }
      if (userInitiated) {
        setOpenReviewsStatus("Loading…", false);
      }
      try {
        const data = await apiGet("/api/open-reviews");
        renderOpenReviews(data, paneEl.openReviewsList);
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
      }
    }

    return {
      setOpenReviewsStatus,
      refreshOpenReviews,
      renderOpenReviews,
      renderOpenReviewCard,
      reviewStateLabel,
    };
  }

  return {
    createOpenReviewsPane,
    renderOpenReviews,
    renderOpenReviewCard,
    reviewStateLabel,
  };
});
