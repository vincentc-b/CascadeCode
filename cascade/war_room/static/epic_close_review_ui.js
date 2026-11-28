(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.EpicCloseReviewUi = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  function append(document, row, actions, review, helpers) {
    if (!review || !review.close_stage) return;

    var stage = review.close_stage;
    var status = document.createElement("span");
    status.className = "epic-close-status epic-close-status-" + stage;
    status.textContent = stage === "implementation_review_pending"
      ? "Implementation review pending"
      : stage === "completed" ? "Close completed" : "Close blocked";
    status.setAttribute("aria-label", "Epic close status: " + status.textContent);
    row.appendChild(status);

    var delivery = review.delivery || {};
    var accepted = delivery.accepted_merge || {};
    var mergeCi = delivery.merge_ci || {};
    var sync = delivery.trunk_sync || {};
    var physicalBoard = delivery.physical_board || {};
    var closure = delivery.verified_closure || {};
    var evidence = document.createElement("div");
    evidence.className = "epic-close-delivery-evidence";
    evidence.textContent =
      "Accepted: " + (accepted.merge_sha || accepted.state || "pending") +
      " · Merge CI: " + (mergeCi.state || "unavailable") +
      " · Trunk: " + (sync.state || "pending") +
      " (local " + (sync.local_sha || "unavailable") +
      ", remote " + (sync.remote_sha || "unavailable") + ")" +
      " · Board: " + (physicalBoard.state || "pending") +
      " · Closure: " + (closure.state || "pending");
    row.appendChild(evidence);

    if (delivery.next_prerequisite) {
      var next = document.createElement("div");
      next.className = "epic-close-next-prerequisite";
      next.textContent = "Next: " + delivery.next_prerequisite;
      row.appendChild(next);
    }

    if (stage !== "completed" && review.review_url) {
      actions.appendChild(helpers.actionLink(
        "Open implementation review",
        review.review_url
      ));
    }

    var blocker = review.blocker;
    if (stage === "blocked" && blocker) {
      var detail = document.createElement("div");
      detail.className = "epic-close-blocker";
      // Forge-provided messages are deliberately assigned as text, never markup.
      detail.textContent = blocker.message;
      row.appendChild(detail);
      if (blocker.retryable === true) {
        actions.appendChild(helpers.actionButton("Finish close", helpers.finishClose));
      }
    }
  }

  return { append: append };
});
