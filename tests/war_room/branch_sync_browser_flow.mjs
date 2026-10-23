/**
 * War Room branch sync browser flow (task_016_002_002).
 *
 * Env:
 *   BRANCH_SYNC_FLOW_PHASE — behind | disabled | update_success | conflict | retry_actions
 *   WAR_ROOM_BASE — loopback War Room origin
 *   WORK_ID — active work id (default feat_001)
 */

import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const BranchSyncUi = require(
  join(repoRoot, "cascade/war_room/static/branch_sync_ui.js")
);

function createElement(tag) {
  const el = {
    tagName: tag.toUpperCase(),
    className: "",
    _text: "",
    title: "",
    disabled: false,
    dataset: {},
    children: [],
    parentNode: null,
    classList: {
      _classes: new Set(),
      add(name) {
        this._classes.add(name);
      },
      toggle(name, force) {
        if (force === undefined) {
          force = !this._classes.has(name);
        }
        if (force) this._classes.add(name);
        else this._classes.delete(name);
      },
      contains(name) {
        return this._classes.has(name);
      },
    },
    setAttribute(name, value) {
      if (name === "role") this.role = value;
      else if (name === "aria-label") this.ariaLabel = value;
      else if (name === "aria-disabled") this.ariaDisabled = value;
      else this[name] = value;
    },
    getAttribute(name) {
      return this[name];
    },
    appendChild(child) {
      child.parentNode = this;
      this.children.push(child);
      return child;
    },
    insertBefore(newChild, refChild) {
      const idx = this.children.indexOf(refChild);
      if (refChild !== null && idx === -1) {
        throw new Error("NotFoundError: reference child is not a child of this node");
      }
      newChild.parentNode = this;
      if (refChild === null) this.children.push(newChild);
      else this.children.splice(idx, 0, newChild);
      return newChild;
    },
    querySelector(sel) {
      if (sel === ".board-row-actions") {
        return this.children.find((c) => c.className === "board-row-actions") || null;
      }
      if (sel === ".branch-sync-recovery") {
        for (const child of this.children) {
          if (child.className === "branch-sync-recovery") return child;
        }
        return null;
      }
      if (sel === '[data-branch-sync-action="update"]') {
        const walk = (node) => {
          if (node.dataset && node.dataset.branchSyncAction === "update") return node;
          for (const c of node.children || []) {
            const hit = walk(c);
            if (hit) return hit;
          }
          return null;
        };
        return walk(this);
      }
      return null;
    },
    addEventListener() {},
    isConnected: true,
  };
  Object.defineProperty(el, "textContent", {
    get() {
      if (el._text) return el._text;
      return (el.children || []).map((c) => c.textContent || "").join("");
    },
    set(value) {
      el._text = value;
      el.children = [];
    },
  });
  Object.defineProperty(el, "firstChild", {
    get() {
      return el.children.length ? el.children[0] : null;
    },
  });
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

function apiGetFromBase(base) {
  return async function apiGet(path) {
    const resp = await fetch(`${base}${path}`, { cache: "no-store" });
    const text = await resp.text();
    const body = JSON.parse(text);
    if (!resp.ok) {
      const err = new Error(body.error || resp.statusText);
      err.status = resp.status;
      err.body = body;
      throw err;
    }
    return body;
  };
}

function apiPostFromBase(base) {
  return async function apiPost(path, payload) {
    const resp = await fetch(`${base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await resp.text();
    let body;
    try {
      body = JSON.parse(text);
    } catch (_e) {
      body = { error: text };
    }
    if (!resp.ok) {
      const err = new Error(body.error || resp.statusText);
      err.status = resp.status;
      err.body = body;
      throw err;
    }
    return { status: resp.status, body };
  };
}

function boardItem(board, tier, workId) {
  const key = { epic: "epics", feature: "features", task: "tasks" }[tier];
  return (board[key]["2_active"] || []).find((item) => item.id === workId);
}

function actionButton(document, label, handler, disabledReason) {
  const btn = createElement("button");
  btn.textContent = label;
  if (disabledReason) {
    btn.disabled = true;
    btn.title = disabledReason;
  }
  btn.addEventListener = function (_ev, fn) {
    btn._handler = fn;
  };
  return btn;
}

function renderRow(document, item, column, helpers) {
  const row = createElement("div");
  row.className = "board-row";
  const actions = createElement("div");
  actions.className = "board-row-actions";
  if (column === "2_active") {
    const closeBtn = actionButton(document, "Close epic", () => Promise.resolve());
    actions.appendChild(closeBtn);
    const mergeBtn = actionButton(document, "Merge task", () => Promise.resolve());
    actions.appendChild(mergeBtn);
    const retryBtn = actionButton(document, "Retry", () => Promise.resolve());
    actions.appendChild(retryBtn);
  }
  helpers.appendBranchSyncToRow(row, item, column, actions);
  row.appendChild(actions);
  return row;
}

async function runPhase(phase) {
  const base = process.env.WAR_ROOM_BASE;
  assert.ok(base, "WAR_ROOM_BASE is required");
  const workId = process.env.WORK_ID || "feat_001";
  const tier = workId.startsWith("epic_")
    ? "epic"
    : workId.startsWith("task_")
      ? "task"
      : "feature";

  const document = { createElement };
  const apiGet = apiGetFromBase(base.replace(/\/$/, ""));
  const apiPost = apiPostFromBase(base.replace(/\/$/, ""));

  let board = await apiGet("/api/board");
  let item = boardItem(board, tier, workId);
  assert.ok(item, `${workId} missing from active board`);

  const helpers = BranchSyncUi.createBranchSyncRowHelpers({
    document,
    apiPost,
    refreshBoard: async () => {
      board = await apiGet("/api/board");
      item = boardItem(board, tier, workId);
    },
    setStatus() {},
    actionButton: (label, handler, disabledReason) =>
      actionButton(document, label, handler, disabledReason),
  });

  if (phase === "behind") {
    const sync = item.branch_sync;
    assert.ok(sync && sync.ok, "expected branch_sync");
    assert.ok(sync.behind > 0, "expected behind > 0");
    const summary = BranchSyncUi.branchSyncSummaryText(sync);
    assert.match(summary, /−\d+/);
    const row = renderRow(document, item, "2_active", helpers);
    const btn = BranchSyncUi.findUpdateBranchButton(row);
    assert.ok(btn, "Update branch button expected");
    assert.equal(btn.disabled, false);
    return;
  }

  if (phase === "disabled") {
    const sync = item.branch_sync;
    assert.ok(sync && sync.behind > 0, "expected behind");
    assert.equal(sync.update_eligible, false, "expected ineligible");
    assert.ok(sync.guidance, "expected guidance");
    const row = renderRow(document, item, "2_active", helpers);
    const btn = BranchSyncUi.findUpdateBranchButton(row);
    assert.ok(btn && btn.disabled, "Update branch should be disabled");
    assert.match(btn.title, /Staged changes block update|Agent turn in progress|Local changes/i);
    return;
  }

  if (phase === "update_success") {
    const row = renderRow(document, item, "2_active", helpers);
    await helpers.runUpdateBranch(workId, row);
    assert.ok(item.branch_sync, "branch_sync after refresh");
    assert.equal(item.branch_sync.behind, 0);
    assert.equal(BranchSyncUi.shouldShowUpdateBranch(item.branch_sync), false);
    const refreshedRow = renderRow(document, item, "2_active", helpers);
    assert.equal(BranchSyncUi.findUpdateBranchButton(refreshedRow), null);
    return;
  }

  if (phase === "conflict") {
    const row = renderRow(document, item, "2_active", helpers);
    await helpers.runUpdateBranch(workId, row);
    const recovery = row.querySelector(".branch-sync-recovery");
    assert.ok(recovery, "expected recovery block");
    const text = recovery.textContent;
    assert.match(text, /Branch conflict/i);
    assert.match(text, /merge was aborted/i);
    assert.match(text, /Blocking paths:/i);
    assert.match(text, /conflict\.txt/);
    assert.ok(!/<<<<<<</.test(text));
    assert.ok(!/>>>>>>>/.test(text));
    return;
  }

  if (phase === "retry_actions") {
    const row = renderRow(document, item, "2_active", helpers);
    const labels = [];
    const walk = (node) => {
      if (node.tagName === "BUTTON") labels.push(node.textContent);
      for (const c of node.children || []) walk(c);
    };
    walk(row);
    assert.ok(labels.includes("Close epic") || labels.includes("Merge task"));
    assert.ok(labels.includes("Retry") || labels.includes("Merge task"));
    return;
  }

  throw new Error(`unknown BRANCH_SYNC_FLOW_PHASE: ${phase}`);
}

const phase = process.env.BRANCH_SYNC_FLOW_PHASE;
assert.ok(phase, "BRANCH_SYNC_FLOW_PHASE is required");
await runPhase(phase);
