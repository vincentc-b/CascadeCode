import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

class FakeElement {
  constructor() {
    this.listeners = new Map();
    this.attributes = new Map();
    this.classNames = new Set();
    this.clientWidth = 0;
    this.textContent = "";
    this.style = {
      values: new Map(),
      setProperty: (name, value) => this.style.values.set(name, value),
    };
    this.classList = {
      add: (name) => this.classNames.add(name),
      remove: (name) => this.classNames.delete(name),
    };
  }

  addEventListener(type, listener) {
    const listeners = this.listeners.get(type) || [];
    listeners.push(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type, listener) {
    this.listeners.set(
      type,
      (this.listeners.get(type) || []).filter((candidate) => candidate !== listener),
    );
  }

  dispatch(type, values = {}) {
    const event = {
      button: 0,
      clientX: 0,
      pointerId: 1,
      preventDefault() {},
      ...values,
    };
    for (const listener of [...(this.listeners.get(type) || [])]) listener(event);
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.get(name) ?? null;
  }

  setPointerCapture() {}
}

function makeStorage(seed) {
  const values = new Map();
  if (seed !== undefined) values.set("cascade-war-room-panel-sizes-v1", seed);
  return {
    getItem(key) { return values.has(key) ? values.get(key) : null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
  };
}

function makeEnvironment(width = 1560) {
  const layout = new FakeElement();
  layout.clientWidth = width;
  const reset = new FakeElement();
  const status = new FakeElement();
  const context = new FakeElement();
  const utilities = new FakeElement();
  const elements = {
    "btn-reset-panel-sizes": reset,
    "panel-size-status": status,
    "context-panel-resizer": context,
    "utilities-panel-resizer": utilities,
  };
  return {
    layout,
    reset,
    status,
    context,
    utilities,
    document: {
      querySelector(selector) { return selector === ".war-room-layout" ? layout : null; },
      getElementById(id) { return elements[id] || null; },
    },
  };
}

globalThis.addEventListener = () => {};
globalThis.matchMedia = () => ({ matches: true });
const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
require(join(repoRoot, "cascade/war_room/static/panel_resizing.js"));

const invalidStorage = makeStorage('{"version":1,"context":"wide","utilities":9999}');
const first = makeEnvironment();
globalThis.PanelResizing.init({
  document: first.document,
  storage: invalidStorage,
  media: { matches: true },
});
assert.equal(first.layout.style.values.get("--context-panel-size"), "320px");
assert.equal(first.layout.style.values.get("--utilities-panel-size"), "320px");
assert.equal(invalidStorage.getItem(globalThis.PanelResizing.storageKey), null);

// Keyboard operation clamps at the accessible maximum and saves both sizes.
first.context.dispatch("keydown", { key: "End" });
assert.equal(first.context.getAttribute("aria-valuenow"), "384");
assert.equal(first.context.getAttribute("aria-valuemax"), "384");

// Dragging the right boundary left grows utilities and clamps at 420px.
first.utilities.dispatch("pointerdown", { clientX: 900 });
first.utilities.dispatch("pointermove", { clientX: 0 });
first.utilities.dispatch("pointerup", { clientX: 0 });
const saved = invalidStorage.getItem(globalThis.PanelResizing.storageKey);
assert.deepEqual(JSON.parse(saved), {
  version: 1,
  context: 384,
  utilities: 420,
});
assert.equal(first.layout.style.values.get("--utilities-panel-size"), "420px");

// A new shell restores valid persisted values, then reset clears the preference.
const restoredStorage = makeStorage(saved);
const restored = makeEnvironment();
globalThis.PanelResizing.init({
  document: restored.document,
  storage: restoredStorage,
  media: { matches: true },
});
assert.equal(restored.layout.style.values.get("--context-panel-size"), "384px");
assert.equal(restored.layout.style.values.get("--utilities-panel-size"), "420px");
restored.reset.dispatch("click");
assert.equal(restored.layout.style.values.get("--context-panel-size"), "320px");
assert.equal(restored.layout.style.values.get("--utilities-panel-size"), "320px");
assert.equal(restoredStorage.getItem(globalThis.PanelResizing.storageKey), null);
assert.equal(restored.status.textContent, "Panel sizes reset to defaults");

// Valid but oversized preferences are fitted to preserve the board minimum.
const constrained = makeEnvironment(1000);
globalThis.PanelResizing.init({
  document: constrained.document,
  storage: makeStorage(saved),
  media: { matches: true },
});
const fittedContext = Number.parseInt(
  constrained.layout.style.values.get("--context-panel-size"),
  10,
);
const fittedUtilities = Number.parseInt(
  constrained.layout.style.values.get("--utilities-panel-size"),
  10,
);
assert.ok(fittedContext >= 224);
assert.ok(fittedUtilities >= 280);
assert.ok(fittedContext + fittedUtilities <= 520);

// Hidden narrow-layout controls ignore keyboard input.
const narrow = makeEnvironment(680);
globalThis.PanelResizing.init({
  document: narrow.document,
  storage: makeStorage(),
  media: { matches: false },
});
narrow.context.dispatch("keydown", { key: "End" });
assert.equal(narrow.context.getAttribute("aria-valuenow"), "224");
