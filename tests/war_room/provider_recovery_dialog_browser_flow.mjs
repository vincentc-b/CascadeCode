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
      classList: {
        add() {},
        remove() {},
        toggle() {},
      },
      addEventListener(name, handler) {
        listeners[name] = handler;
      },
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
  document: {
    createElement() { return control({ selected: false }); },
  },
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
      "  function populateProviderRecoveryProviders()",
      "  function buildRow(item, tier, column)"
    )}
    ({
      changeProviderRecovery,
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
  provider_recovery: {
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

inventoryRequest = { promise: Promise.resolve(inventory) };
await dialog.changeProviderRecovery(item);
const savedSelection = JSON.parse(JSON.stringify(dialog.state().selection));
nextRecoveryRequest = deferred();
const firstSubmit = dialog.submitProviderRecovery({ preventDefault() {} });
const duplicateSubmit = dialog.submitProviderRecovery({ preventDefault() {} });
assert.equal(recoveryRequests.length, 1, "an in-flight change suppresses duplicate submits");
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
assert.deepEqual(recoveryRequests[1], {
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
assert.equal(refreshCount, 1);

inventoryRequest = { promise: Promise.reject(new Error("inventory offline")) };
await dialog.changeProviderRecovery(item);
assert.match(el.providerRecoveryStatus.textContent, /Could not refresh model inventory/);
assert.equal(el.btnProviderRecoveryInventoryRetry.hidden, false);
await dialog.retryProviderRecoveryInventory();
assert.match(el.providerRecoveryStatus.textContent, /Could not refresh model inventory/);
assert.equal(el.btnProviderRecoveryInventoryRetry.hidden, false);

console.log("provider_recovery_dialog_browser_flow: ok");
