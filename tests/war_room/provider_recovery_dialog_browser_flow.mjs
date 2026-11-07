import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const source = readFileSync(
  join(repoRoot, "cascade/war_room/static/war_room.js"),
  "utf8"
);
const ProviderRecoveryDialogUi = require(join(
  repoRoot,
  "cascade/war_room/static/provider_recovery_dialog_ui.js"
));
const briefUi = require(join(
  repoRoot,
  "cascade/war_room/static/brief_defaults_ui.js"
));

function sourceSection(start, end) {
  const first = source.indexOf(start);
  const last = source.indexOf(end, first);
  assert.ok(first >= 0 && last > first, `missing script section: ${start}`);
  return source.slice(first, last);
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

function control(extra = {}) {
  const listeners = {};
  return Object.assign(
    {
      checked: false,
      children: [],
      disabled: false,
      hidden: false,
      textContent: "",
      value: "",
      isConnected: true,
      classList: {
        add() {},
        remove() {},
        toggle() {},
      },
      addEventListener(name, handler) {
        listeners[name] = handler;
      },
      focus() { this.focused = true; },
      appendChild(child) {
        this.children.push(child);
        if (child.selected) this.value = child.value;
      },
      replaceChildren(...children) {
        this.children = children;
      },
      querySelectorAll() {
        return [];
      },
      listeners,
    },
    extra
  );
}

const inventory = {
  loading: false,
  default_provider: "codex",
  providers: [
    {
      id: "codex",
      display_name: "Codex",
      supports_flex_mode: true,
      models: [
        {
          id: "worker",
          display_name: "Worker",
          reasoning: {
            default_level: "medium",
            override_levels: ["high"],
            default_only: false,
          },
        },
      ],
    },
  ],
  refresh: { failed: false },
};

const el = {
  providerRecoveryDialog: control({
    open: false,
    closeCount: 0,
    showModal() { this.open = true; },
    close() { this.open = false; this.closeCount += 1; },
  }),
  providerRecoveryTitle: control(),
  providerRecoverySummary: control(),
  providerRecoveryPartial: control(),
  providerRecoveryFailure: control(),
  providerRecoveryFailureSummary: control(),
  providerRecoveryFailureMeta: control(),
  providerRecoveryFailureChecks: control(),
  providerRecoveryReadinessSummary: control(),
  providerRecoveryReadinessFreshness: control(),
  providerRecoverySelection: control(),
  providerRecoveryRemedies: control(),
  providerRecoveryStatus: control(),
  providerRecoveryProvider: control(),
  providerRecoveryFlexMode: control(),
  providerRecoveryFlexModeWrap: control(),
  providerRecoveryFlexModeNote: control(),
  providerRecoveryRoleSelectors: control(),
  btnProviderRecoveryInventoryRetry: control(),
  btnCloseProviderRecovery: control(),
  btnCancelProviderRecovery: control(),
  btnSubmitProviderRecovery: control(),
};

let inventoryRequest = deferred();
const recoveryRequests = [];
let nextRecoveryRequest = null;
let refreshCount = 0;
let renderedRoles = [];

const BriefDefaultsUi = Object.assign({}, briefUi, {
  renderRoleSelectors(_container, _inventory, _template, _selection, _handlers, options) {
    renderedRoles = options.roles.slice();
  },
});

const context = {
  BriefDefaultsUi,
  ProviderRecoveryDialogUi,
  el,
  lastInvokedBoardAction: null,
  document: {
    activeElement: control(),
    createElement() { return control({ selected: false }); },
  },
  lastBoardView: null,
  providerRecoveryAction(recovery, name) {
    return !!(recovery && recovery.actions && recovery.actions[name] && recovery.actions[name].eligible);
  },
  readinessAction(readiness, name) {
    return !!(readiness && readiness.actions && readiness.actions[name] && readiness.actions[name].eligible);
  },
  retryProviderRecovery() { return Promise.resolve({ ok: false }); },
  openProviderSetup() { return Promise.resolve(); },
  openBriefEdit() { return Promise.resolve(); },
  apiGet(path) {
    assert.equal(path, "/api/brief/inventory");
    return inventoryRequest.promise;
  },
  apiPost(path, payload) {
    if (path === "/api/brief/inventory/refresh") {
      return Promise.reject(new Error("inventory offline"));
    }
    recoveryRequests.push({ path, payload });
    return nextRecoveryRequest.promise;
  },
  refreshBoard() {
    refreshCount += 1;
    return Promise.resolve();
  },
  setStatus() {},
  encodeURIComponent,
};

const dialog = vm.runInNewContext(
  `
    let providerRecoveryTarget = null;
    let providerRecoveryInventory = null;
    let providerRecoverySelection = null;
    let providerRecoverySubmitInFlight = false;
    let providerRecoveryError = "";
    let providerRecoveryLoadToken = 0;
    ${sourceSection(
      "  async function continueProviderRecoveryWithoutFlex(item)",
      "  function buildRow(item, tier, column)"
    )}
    ({
      changeProviderRecovery,
      continueProviderRecoveryWithoutFlex,
      retryProviderRecoveryInventory,
      submitProviderRecovery,
      closeProviderRecoveryDialog,
      state() {
        return {
          selection: providerRecoverySelection,
          inFlight: providerRecoverySubmitInFlight,
          error: providerRecoveryError,
        };
      },
    });
  `,
  context
);

const item = {
  id: "task_001",
  tier: "task",
  provider_readiness: {
    outcome: "transient",
    message: "Provider capability could not be confirmed.",
    inventory_freshness: { stale: true, fetched_at: null },
    actions: { refresh: { eligible: true } },
  },
  provider_recovery: {
    actions: {
      change_provider: { eligible: true },
      continue_without_flex: {
        eligible: true,
        action_id: "attempt-7",
        document_revision: "revision-7",
        selection_fingerprint: "fingerprint-7",
      },
    },
    selection: {
      provider: "codex",
      models: { swe: "worker" },
      reasoning: { swe: "high" },
      flex_mode: true,
    },
  },
};

const opening = dialog.changeProviderRecovery(item);
assert.equal(el.providerRecoveryDialog.open, true);
assert.match(el.providerRecoveryStatus.textContent, /Loading available providers/);
assert.equal(el.btnSubmitProviderRecovery.disabled, true);
inventoryRequest.resolve(inventory);
await opening;
assert.deepEqual(renderedRoles, ["swe"]);
assert.equal(el.providerRecoveryFlexModeWrap.hidden, false);
assert.equal(el.btnSubmitProviderRecovery.disabled, false);

const beforeCancelRequests = recoveryRequests.length;
dialog.closeProviderRecoveryDialog();
assert.equal(el.providerRecoveryDialog.open, false);
assert.equal(recoveryRequests.length, beforeCancelRequests);

nextRecoveryRequest = deferred();
const continued = dialog.continueProviderRecoveryWithoutFlex(item);
assert.deepEqual(JSON.parse(JSON.stringify(recoveryRequests[0])), {
  path: "/api/provider-recovery/task_001/continue-without-flex",
  payload: {
    failed_action_id: "attempt-7",
    expected_document_revision: "revision-7",
    expected_selection_fingerprint: "fingerprint-7",
  },
});
nextRecoveryRequest.resolve({ body: { ok: true, state: "completed", receipt_id: "receipt-7" } });
assert.equal((await continued).receipt_id, "receipt-7");
assert.equal(refreshCount, 1);

inventoryRequest = { promise: Promise.resolve(inventory) };
await dialog.changeProviderRecovery(item);
const savedSelection = JSON.parse(JSON.stringify(dialog.state().selection));
nextRecoveryRequest = deferred();
const firstSubmit = dialog.submitProviderRecovery({ preventDefault() {} });
const duplicateSubmit = dialog.submitProviderRecovery({ preventDefault() {} });
assert.equal(recoveryRequests.length, 2, "an in-flight change suppresses duplicate submits");
assert.equal(dialog.state().inFlight, true);
assert.equal(el.btnCancelProviderRecovery.disabled, true);
assert.equal(el.btnSubmitProviderRecovery.disabled, true);
nextRecoveryRequest.reject({ body: { reason: "Selection changed on the server." } });
assert.equal(await firstSubmit, null);
await duplicateSubmit;
assert.equal(el.providerRecoveryDialog.open, true);
assert.match(el.providerRecoveryStatus.textContent, /Selection changed on the server/);
assert.deepEqual(dialog.state().selection, savedSelection);
assert.equal(el.btnSubmitProviderRecovery.disabled, false);

nextRecoveryRequest = deferred();
const successfulSubmit = dialog.submitProviderRecovery({ preventDefault() {} });
assert.deepEqual(recoveryRequests[2], {
  path: "/api/provider-recovery/task_001/change",
  payload: {
    provider: "codex",
    models: { swe: "worker" },
    flex_mode: true,
    reasoning: { swe: "high" },
  },
});
nextRecoveryRequest.resolve({ body: { ok: true } });
await successfulSubmit;
assert.equal(el.providerRecoveryDialog.open, false);
assert.equal(refreshCount, 2);

inventoryRequest = { promise: Promise.reject(new Error("inventory offline")) };
await dialog.changeProviderRecovery(item);
assert.match(el.providerRecoveryStatus.textContent, /Could not refresh model inventory/);
assert.equal(el.btnProviderRecoveryInventoryRetry.hidden, true);
assert.ok(el.providerRecoveryRemedies.children.some((child) => child.textContent === "Refresh provider inventory"));
await dialog.retryProviderRecoveryInventory();
assert.match(el.providerRecoveryStatus.textContent, /Could not refresh model inventory/);
assert.equal(el.btnProviderRecoveryInventoryRetry.hidden, true);

console.log("provider_recovery_dialog_browser_flow: ok");
