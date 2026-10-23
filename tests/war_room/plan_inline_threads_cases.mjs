import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createElement, installPlanCommentDom, querySelectorAll } from "./plan_dom_fixture.mjs";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const staticDir = join(repoRoot, "cascade/war_room/static");

globalThis.marked = require(join(staticDir, "vendor/marked.min.js"));
const { markdownToHtml, initPlanComments } = require(join(staticDir, "plan_viewer.js"));

const partitionDoc = `# Plan

## Scope

Alpha snippet here.

## Other

Tail.
`;

const docSha = "live-sha";

function findDescendant(root, selector) {
  if (matchesSelector(root, selector)) return root;
  for (const child of root.children || []) {
    const hit = findDescendant(child, selector);
    if (hit) return hit;
  }
  return null;
}

function matchesSelector(el, selector) {
  const trimmed = selector.trim();
  const spaceIdx = trimmed.indexOf(" ");
  if (spaceIdx >= 0) {
    const parentSel = trimmed.slice(0, spaceIdx);
    const childSel = trimmed.slice(spaceIdx + 1);
    if (!matchesSelector(el, childSel)) return false;
    let parent = el.parentNode;
    while (parent) {
      if (matchesSelector(parent, parentSel)) return true;
      parent = parent.parentNode;
    }
    return false;
  }
  if (trimmed.startsWith(".")) {
    const rest = trimmed.slice(1);
    const dotIdx = rest.indexOf("[");
    if (dotIdx >= 0) {
      const cls = rest.slice(0, dotIdx);
      const attrPart = rest.slice(dotIdx);
      return el.classList.contains(cls) && matchesSelector(el, attrPart);
    }
    return el.classList.contains(rest);
  }
  if (trimmed.startsWith("[")) {
    const attrMatch = trimmed.match(/^\[([^\]=]+)(?:="([^"]*)")?\]$/);
    if (!attrMatch) return false;
    const [, attr, value] = attrMatch;
    if (value === undefined) return el.getAttribute(attr) != null;
    return el.getAttribute(attr) === value;
  }
  if (/^[a-z0-9-]+$/i.test(trimmed)) {
    return el.tagName === trimmed.toUpperCase();
  }
  return false;
}

function planThreadsIn(rootEl) {
  return querySelectorAll(rootEl, ".plan-comment-thread").filter((el) =>
    el.getAttribute("data-comment-id")
  );
}

function threadById(rootEl, id) {
  return planThreadsIn(rootEl).find((el) => el.getAttribute("data-comment-id") === id) || null;
}

function threadIdsInDocument(rootEl) {
  return planThreadsIn(rootEl).map((el) => el.getAttribute("data-comment-id"));
}

function textContentDeep(el) {
  if (!el) return "";
  let out = el.textContent || "";
  for (const child of el.children || []) {
    out += textContentDeep(child);
  }
  return out;
}

function inlineContainersAfterBlock(bodyEl, line) {
  const block = bodyEl.querySelector(`[data-src-line="${line}"]`);
  assert.ok(block, `missing block for line ${line}`);
  let sibling = block.nextSibling;
  const containers = [];
  while (sibling && sibling.classList.contains("plan-inline-threads")) {
    containers.push(sibling);
    sibling = sibling.nextSibling;
  }
  return containers;
}

function populateBodyFromMarkdown(bodyEl, docBody) {
  const html = markdownToHtml(docBody);
  for (const line of html.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const matched = trimmed.match(/^<([a-z0-9]+)([^>]*)>([\s\S]*)<\/\1>$/i);
    if (!matched) continue;
    const [, tag, attrs, text] = matched;
    const el = createElement(tag);
    const attrRe = /([a-z0-9-]+)="([^"]*)"/gi;
    let attrMatch;
    while ((attrMatch = attrRe.exec(attrs))) {
      el.setAttribute(attrMatch[1], attrMatch[2]);
    }
    el.textContent = text;
    bodyEl.appendChild(el);
  }
}

function setupPlanBody(docBody) {
  const dom = installPlanCommentDom();
  populateBodyFromMarkdown(dom.bodyEl, docBody);
  return dom;
}

function mountComments(tier, docBody, comments) {
  const dom = setupPlanBody(docBody);
  const hooks = initPlanComments("doc_under_test", tier, {
    testHooks: true,
    bodyEl: dom.bodyEl,
    docBody,
    docSha,
  });
  assert.ok(hooks && hooks.renderComments, "expected test hooks from initPlanComments");
  hooks.renderComments(comments);
  return { dom, hooks };
}

function baseInlineComments() {
  return [
    {
      id: "cmt_a",
      section: "scope",
      anchor: "Alpha snippet here",
      line_start: 5,
      line_end: 5,
      doc_sha: docSha,
      body: "first",
      author: "human",
    },
    {
      id: "cmt_b",
      section: "scope",
      anchor: "Alpha snippet here",
      line_start: 5,
      line_end: 5,
      doc_sha: docSha,
      body: "second",
      author: "human",
    },
    { id: "cmt_global", section: "general", body: "whole plan", line_start: null, author: "human" },
    {
      id: "cmt_outdated_inline",
      section: "scope",
      anchor: "deleted text",
      line_start: 4,
      line_end: 4,
      doc_sha: "old-sha",
      body: "outdated but inline",
      author: "human",
    },
  ];
}

function assertEpicOrFeatureInitialInline(tier) {
  const comments = baseInlineComments();
  const { dom } = mountComments(tier, partitionDoc, comments);
  const inlineOnFive = inlineContainersAfterBlock(dom.bodyEl, "5");
  assert.equal(inlineOnFive.length, 1);
  const inlineIds = threadIdsInDocument(inlineOnFive[0]);
  assert.deepEqual(inlineIds, ["cmt_a", "cmt_b"]);

  const outdatedBlock = dom.bodyEl.querySelector('[data-src-line="3"]');
  const outdatedContainer = outdatedBlock.nextSibling;
  assert.ok(outdatedContainer && outdatedContainer.classList.contains("plan-inline-threads"));
  assert.deepEqual(threadIdsInDocument(outdatedContainer), ["cmt_outdated_inline"]);
  const outdatedThread = threadById(outdatedContainer, "cmt_outdated_inline");
  assert.ok(outdatedThread, "relocatable outdated thread stays inline");
  assert.ok(
    outdatedThread.classList.contains("outdated"),
    "relocatable outdated thread keeps outdated styling"
  );

  const trayIds = threadIdsInDocument(dom.threadEl);
  assert.deepEqual(trayIds, ["cmt_global"]);
  assert.equal(threadIdsInDocument(dom.bodyEl.parentNode || dom.bodyEl).length, 3);
}

assertEpicOrFeatureInitialInline("epic");
assertEpicOrFeatureInitialInline("feature");

// Task pages skip inline reconciliation entirely.
{
  const dom = installPlanCommentDom();
  const hooks = initPlanComments("task_001", "task", {
    testHooks: true,
    bodyEl: dom.bodyEl,
    docBody: partitionDoc,
    docSha,
  });
  assert.equal(hooks.skipped, true);
  assert.equal(dom.threadEl.children.length, 0);
}

// Repeated renders do not duplicate or reorder threads.
{
  const comments = baseInlineComments();
  const { dom, hooks } = mountComments("feature", partitionDoc, comments);
  hooks.renderComments(comments);
  hooks.renderComments(comments);
  const allIds = threadIdsInDocument(document.getElementById("plan-body"));
  assert.deepEqual(
    allIds.filter((id) => id === "cmt_a" || id === "cmt_b"),
    ["cmt_a", "cmt_b"]
  );
  assert.equal(allIds.filter((id) => id === "cmt_a").length, 1);
  assert.equal(allIds.filter((id) => id === "cmt_b").length, 1);
  assert.equal(inlineContainersAfterBlock(dom.bodyEl, "5").length, 1);
}

// Tray fallback: whole-plan roots and anchors with no safe inline block (once each).
{
  const dom = installPlanCommentDom();
  populateBodyFromMarkdown(dom.bodyEl, partitionDoc);
  // Drop the title block so relocated anchors cannot mount on line 1.
  const titleBlock = dom.bodyEl.querySelector('[data-src-line="1"]');
  if (titleBlock) titleBlock.remove();
  const comments = [
    { id: "cmt_global", section: "general", body: "whole plan", line_start: null, author: "human" },
    {
      id: "cmt_unplaceable",
      section: "missing-section",
      anchor: "nowhere",
      line_start: 2,
      line_end: 2,
      doc_sha: "old-sha",
      body: "tray fallback",
      author: "human",
    },
    {
      id: "cmt_missing",
      section: "my-doc",
      anchor: "nowhere",
      line_start: 2,
      line_end: 2,
      doc_sha: "old-sha",
      body: "missing anchor",
      author: "human",
    },
  ];
  const hooks = initPlanComments("feat_tray", "feature", {
    testHooks: true,
    bodyEl: dom.bodyEl,
    docBody: partitionDoc,
    docSha,
  });
  hooks.renderComments(comments);
  const trayIds = threadIdsInDocument(dom.threadEl);
  assert.deepEqual(trayIds.sort(), ["cmt_global", "cmt_missing", "cmt_unplaceable"]);
  assert.equal(querySelectorAll(dom.bodyEl, ".plan-inline-threads").length, 0);
  for (const id of trayIds) {
    assert.equal(
      dom.threadEl.querySelectorAll(`[data-comment-id="${id}"]`).length,
      1,
      "tray thread rendered once"
    );
  }
}

// Post/refresh reconciliation: one new inline root without duplicating on reload.
{
  const dom = setupPlanBody(partitionDoc);
  let stored = [];
  globalThis.fetch = async function (url) {
    if (String(url).includes("/api/comments/")) {
      return {
        ok: true,
        json: async () => ({ comments: stored }),
      };
    }
    throw new Error(`unexpected fetch: ${url}`);
  };
  const hooks = initPlanComments("feat_post", "feature", {
    testHooks: true,
    bodyEl: dom.bodyEl,
    docBody: partitionDoc,
    docSha,
  });
  stored = [
    {
      id: "cmt_new",
      section: "scope",
      anchor: "Alpha snippet here",
      line_start: 5,
      line_end: 5,
      doc_sha: docSha,
      body: "posted inline",
      author: "human",
    },
  ];
  await hooks.loadComments();
  const inline = inlineContainersAfterBlock(dom.bodyEl, "5");
  assert.equal(inline.length, 1);
  assert.deepEqual(threadIdsInDocument(inline[0]), ["cmt_new"]);
  await hooks.loadComments();
  assert.deepEqual(threadIdsInDocument(inline[0]), ["cmt_new"]);
  assert.equal(threadIdsInDocument(inline[0]).filter((id) => id === "cmt_new").length, 1);
  delete globalThis.fetch;
}

// Reply and resolve refresh in place; unrelated reply drafts survive reconciliation.
{
  const comments = [
    {
      id: "cmt_root",
      section: "scope",
      anchor: "Alpha snippet here",
      line_start: 5,
      line_end: 5,
      doc_sha: docSha,
      body: "root",
      author: "human",
      state: "open",
    },
    {
      id: "cmt_other",
      section: "scope",
      anchor: "Alpha snippet here",
      line_start: 5,
      line_end: 5,
      doc_sha: docSha,
      body: "other root",
      author: "human",
      state: "open",
    },
  ];
  const { dom, hooks } = mountComments("feature", partitionDoc, comments);
  const otherThread = threadById(dom.bodyEl, "cmt_other");
  assert.ok(otherThread, "expected sibling inline thread");
  const draftInput = findDescendant(otherThread, "textarea");
  assert.ok(draftInput, "expected reply draft field on sibling thread");
  draftInput.value = "keep this draft";
  hooks.renderComments([
    {
      ...comments[0],
      body: "root",
      state: "open",
    },
    {
      id: "cmt_reply",
      parent: "cmt_root",
      body: "new reply",
      author: "human",
      state: "open",
    },
    comments[1],
  ]);
  const rootThread = threadById(dom.bodyEl, "cmt_root");
  assert.ok(findDescendant(rootThread, ".plan-comment-replies"));
  assert.match(textContentDeep(rootThread), /new reply/);
  const otherAfter = threadById(dom.bodyEl, "cmt_other");
  assert.equal(findDescendant(otherAfter, "textarea").value, "keep this draft");

  hooks.renderComments([
    { ...comments[0], state: "resolved" },
    {
      id: "cmt_reply",
      parent: "cmt_root",
      body: "new reply",
      author: "human",
      state: "resolved",
    },
    comments[1],
  ]);
  const resolvedThread = threadById(dom.bodyEl, "cmt_root");
  assert.ok(resolvedThread.classList.contains("resolved"));
  assert.equal(resolvedThread.querySelector(".plan-comment-resolve"), null);
}

// Inline controls stay keyboard-focusable (native buttons/textarea, no tabIndex=-1).
{
  const { dom } = mountComments("epic", partitionDoc, baseInlineComments().slice(0, 1));
  const thread = planThreadsIn(dom.bodyEl)[0];
  for (const control of [
    ...querySelectorAll(thread, "button"),
    ...querySelectorAll(thread, "textarea"),
  ]) {
    assert.notEqual(control.getAttribute("tabindex"), "-1");
  }
}

// Status region receives resolve/reply announcements via existing status element.
{
  const dom = installPlanCommentDom();
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({ comments: [] }),
  });
  const hooks = initPlanComments("feat_status", "feature", {
    testHooks: true,
    bodyEl: dom.bodyEl,
    docBody: partitionDoc,
    docSha,
  });
  assert.equal(dom.statusEl.getAttribute("role"), "status");
  await hooks.loadComments();
  delete globalThis.fetch;
}

// Narrow viewport CSS keeps inline layout from forcing horizontal scroll.
{
  const css = readFileSync(join(staticDir, "plan_viewer.css"), "utf8");
  assert.match(css, /\.plan-inline-threads[\s\S]*max-width:\s*100%/);
  assert.match(css, /overflow-wrap:\s*anywhere/);
  assert.match(css, /@media \(max-width: 36rem\)[\s\S]*\.plan-inline-threads/);
}

console.log("plan_inline_threads cases ok");
