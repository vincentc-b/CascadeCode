/**
 * Lifecycle sandbox browser flow for open merge requests (task_013).
 *
 * Env:
 *   OPEN_REVIEWS_FLOW_PHASE — empty | open | closed | failure
 *   WAR_ROOM_BASE — loopback War Room origin (required except failure)
 *   EXPECT_REVIEW_URL — direct review link when phase is open
 *   EXPECT_FEATURE_ID — feature id when phase is open
 *   EXPECT_FEATURE_TITLE — feature title when phase is open
 *   EXPECT_EPIC_TITLE — epic title when phase is open
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const { createOpenReviewsPane } = require(
  join(repoRoot, "cascade/war_room/static/open_reviews_pane.js")
);

function createElement(tag) {
  const el = {
    tagName: tag,
    className: "",
    textContent: "",
    id: "",
    href: "",
    target: "",
    rel: "",
    disabled: false,
    children: [],
    dataset: {},
    classList: {
      _error: false,
      toggle(name, force) {
        if (name === "error") {
          this._error = force !== undefined ? !!force : !this._error;
        }
      },
      contains(name) {
        return name === "error" ? this._error : false;
      },
    },
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    addEventListener() {},
    setAttribute() {},
  };
  Object.defineProperty(el, "innerHTML", {
    set() {
      el.children = [];
    },
    get() {
      return "";
    },
  });
  return el;
}

function findByClass(root, className) {
  if (root.className === className) return root;
  for (const child of root.children || []) {
    const hit = findByClass(child, className);
    if (hit) return hit;
  }
  return null;
}

function findLink(root, label) {
  for (const child of root.children || []) {
    if (child.tagName === "a" && child.textContent === label) return child;
    const nested = findLink(child, label);
    if (nested) return nested;
  }
  return null;
}

function installDom() {
  const openReviewsStatus = createElement("p");
  openReviewsStatus.id = "open-reviews-status";
  const openReviewsList = createElement("ul");
  openReviewsList.id = "open-reviews-list";
  const btnRefreshOpenReviews = createElement("button");
  btnRefreshOpenReviews.id = "btn-refresh-open-reviews";
  globalThis.document = {
    getElementById(id) {
      if (id === "open-reviews-status") return openReviewsStatus;
      if (id === "open-reviews-list") return openReviewsList;
      if (id === "btn-refresh-open-reviews") return btnRefreshOpenReviews;
      return null;
    },
    createElement,
  };
  return { openReviewsStatus, openReviewsList, btnRefreshOpenReviews };
}

function apiGetFromBase(base) {
  return async function apiGet(path) {
    const resp = await fetch(`${base}${path}`, { cache: "no-store" });
    const text = await resp.text();
    let body;
    try {
      body = JSON.parse(text);
    } catch (_e) {
      body = text;
    }
    if (!resp.ok) {
      const err = new Error(
        typeof body === "object" && body.error ? body.error : resp.statusText
      );
      err.status = resp.status;
      throw err;
    }
    return body;
  };
}

async function runPhase(phase) {
  const dom = installDom();

  if (phase === "failure") {
    const pane = createOpenReviewsPane({
      elements: dom,
      apiGet: async () => {
        throw new Error("network down");
      },
    });
    await pane.refreshOpenReviews({ userInitiated: true });
    assert.match(dom.openReviewsStatus.textContent, /network down/i);
    assert(dom.openReviewsStatus.classList.contains("error"));
    assert.equal(dom.openReviewsList.children.length, 0);
    return;
  }

  const base = process.env.WAR_ROOM_BASE;
  assert.ok(base, "WAR_ROOM_BASE is required");
  const pane = createOpenReviewsPane({
    elements: dom,
    apiGet: apiGetFromBase(base.replace(/\/$/, "")),
  });

  if (phase === "empty" || phase === "closed") {
    await pane.refreshOpenReviews({ userInitiated: false });
    const empty = findByClass(dom.openReviewsList, "open-reviews-empty");
    assert.ok(empty, "expected empty-state row");
    assert.match(dom.openReviewsStatus.textContent, /0 open merge requests/i);
    return;
  }

  if (phase === "open") {
    await pane.refreshOpenReviews({ userInitiated: true });
    const card = findByClass(dom.openReviewsList, "open-review-card");
    assert.ok(card, "expected open review card");
    const title = findByClass(card, "open-review-feature-title");
    const context = findByClass(card, "open-review-context");
    assert.equal(title.textContent, process.env.EXPECT_FEATURE_TITLE);
    assert.match(context.textContent, new RegExp(process.env.EXPECT_FEATURE_ID));
    assert.match(context.textContent, new RegExp(process.env.EXPECT_EPIC_TITLE));
    const link = findLink(card, "Open review");
    assert.ok(link, "expected direct review link");
    assert.equal(link.href, process.env.EXPECT_REVIEW_URL);
    assert.equal(link.target, "_blank");
    assert.match(dom.openReviewsStatus.textContent, /1 open merge request/i);
    return;
  }

  throw new Error(`unknown OPEN_REVIEWS_FLOW_PHASE: ${phase}`);
}

const phase = process.env.OPEN_REVIEWS_FLOW_PHASE;
assert.ok(phase, "OPEN_REVIEWS_FLOW_PHASE is required");
await runPhase(phase);
