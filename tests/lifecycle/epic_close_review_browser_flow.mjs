/** Browser contract for durable epic close-review controls against a live War Room. */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const ui = require(join(repoRoot, "cascade/war_room/static/epic_close_review_ui.js"));

function element(tagName) {
  return {
    tagName,
    children: [],
    attributes: {},
    className: "",
    textContent: "",
    appendChild(child) { this.children.push(child); return child; },
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}

function find(root, predicate) {
  if (predicate(root)) return root;
  for (const child of root.children || []) {
    const match = find(child, predicate);
    if (match) return match;
  }
  return null;
}

function epicFrom(board, epicId) {
  for (const rows of Object.values(board.epics)) {
    const epic = rows.find((row) => row.id === epicId);
    if (epic) return epic;
  }
  assert.fail(`epic ${epicId} missing from board`);
}

async function request(path, options) {
  const response = await fetch(`${base}${path}`, options);
  const body = await response.json();
  assert.equal(response.status, 200, JSON.stringify(body));
  return body;
}

async function renderFromBoard() {
  const board = await request("/api/board");
  const review = epicFrom(board, epicId).implementation_review;
  const row = element("div");
  const actions = element("div");
  ui.append(globalThis.document, row, actions, review, {
    actionLink(label, href) {
      const link = element("a");
      link.textContent = label;
      link.href = href;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      return link;
    },
    actionButton(label, callback) {
      const button = element("button");
      button.textContent = label;
      button.callback = callback;
      return button;
    },
    async finishClose() {
      return request("/api/confirm_epic_complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: epicId }),
      });
    },
  });
  return { review, row, actions };
}

function assertPending(rendered) {
  assert.equal(rendered.review.close_stage, "implementation_review_pending");
  assert.equal(rendered.row.children[0].textContent, "Implementation review pending");
  assert.equal(
    rendered.row.children[0].attributes["aria-label"],
    "Epic close status: Implementation review pending",
  );
  const link = find(rendered.actions, (node) =>
    node.tagName === "a" && node.textContent === "Open implementation review");
  assert.ok(link, "pending review link should be accessible");
  assert.equal(link.href, reviewUrl);
  assert.equal(link.target, "_blank");
  assert.match(link.rel, /noopener/);
  assert.match(link.rel, /noreferrer/);
}

globalThis.document = { createElement: element };
const base = process.env.WAR_ROOM_BASE?.replace(/\/$/, "");
const epicId = process.env.EPIC_ID;
const reviewUrl = process.env.EXPECT_REVIEW_URL;
const phase = process.env.EPIC_CLOSE_FLOW_PHASE;
assert.ok(base && epicId && reviewUrl && phase, "browser flow environment is incomplete");

if (phase === "pending") {
  // A second render represents both a board refresh and returning to the board
  // after navigation: neither relies on client-only state.
  assertPending(await renderFromBoard());
  assertPending(await renderFromBoard());
} else if (phase === "blocked_finish") {
  const blocked = await renderFromBoard();
  assert.equal(blocked.review.close_stage, "blocked");
  assert.equal(blocked.row.children[0].textContent, "Close blocked");
  const detail = find(blocked.row, (node) => node.className === "epic-close-blocker");
  assert.ok(detail, "actionable blocker detail should be visible");
  assert.equal(detail.textContent, process.env.EXPECT_BLOCKER_MESSAGE);
  assert.equal(detail.children.length, 0, "forge text must not be interpreted as HTML");
  const finish = find(blocked.actions, (node) =>
    node.tagName === "button" && node.textContent === "Finish close");
  assert.ok(finish, "retryable blocker should expose Finish close");
  const response = await finish.callback();
  assert.equal(response.ok, true);

  const completed = await renderFromBoard();
  assert.equal(completed.review.close_stage, "completed");
  assert.equal(completed.row.children[0].textContent, "Close completed");
  assert.equal(completed.actions.children.length, 0,
    "completed close should replace pending review controls");
} else {
  assert.fail(`unknown EPIC_CLOSE_FLOW_PHASE: ${phase}`);
}
