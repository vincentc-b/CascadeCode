(function (global) {
  "use strict";

  const STORAGE_KEY = "cascade-war-room-panel-sizes-v1";
  const VERSION = 1;
  const WIDE_LAYOUT_QUERY = "(min-width: 1241px)";
  const BOARD_MIN = 448;
  const RESIZER_SPACE = 32;
  const KEYBOARD_STEP = 16;
  const STORED_SIZE_LIMIT = 16384;
  const LIMITS = {
    context: { min: 224, defaultSize: 320 },
    utilities: { min: 280, defaultSize: 320 },
  };

  function clamp(value, min, max) {
    return Math.min(Math.max(value, min), max);
  }

  function validStoredSizes(value) {
    return Boolean(
      value &&
        value.version === VERSION &&
        Number.isFinite(value.context) &&
        value.context >= LIMITS.context.min &&
        value.context <= STORED_SIZE_LIMIT &&
        Number.isFinite(value.utilities) &&
        value.utilities >= LIMITS.utilities.min &&
        value.utilities <= STORED_SIZE_LIMIT
    );
  }

  function defaults() {
    return {
      context: LIMITS.context.defaultSize,
      utilities: LIMITS.utilities.defaultSize,
    };
  }

  function readSizes(storage) {
    try {
      const raw = storage.getItem(STORAGE_KEY);
      if (raw === null) return defaults();
      const parsed = JSON.parse(raw);
      if (validStoredSizes(parsed)) {
        return { context: parsed.context, utilities: parsed.utilities };
      }
      storage.removeItem(STORAGE_KEY);
    } catch (_error) {
      // Storage may be blocked or contain malformed data. Defaults remain safe.
    }
    return defaults();
  }

  function init(options) {
    const config = options || {};
    const doc = config.document || global.document;
    if (!doc) return null;

    const layout = doc.querySelector(".war-room-layout");
    const reset = doc.getElementById("btn-reset-panel-sizes");
    const status = doc.getElementById("panel-size-status");
    const handles = {
      context: doc.getElementById("context-panel-resizer"),
      utilities: doc.getElementById("utilities-panel-resizer"),
    };
    if (!layout || !reset || !handles.context || !handles.utilities) return null;

    let storage;
    try {
      storage = config.storage || global.localStorage;
    } catch (_error) {
      storage = null;
    }
    const media = config.media || global.matchMedia(WIDE_LAYOUT_QUERY);
    let preferred = storage ? readSizes(storage) : defaults();
    let applied = defaults();

    function availableForPanels() {
      return Math.max(
        LIMITS.context.min + LIMITS.utilities.min,
        layout.clientWidth - BOARD_MIN - RESIZER_SPACE
      );
    }

    function fitToViewport(sizes) {
      let context = clamp(sizes.context, LIMITS.context.min, STORED_SIZE_LIMIT);
      let utilities = clamp(sizes.utilities, LIMITS.utilities.min, STORED_SIZE_LIMIT);
      let overflow = context + utilities - availableForPanels();
      if (overflow > 0) {
        const utilitiesReduction = Math.min(overflow, utilities - LIMITS.utilities.min);
        utilities -= utilitiesReduction;
        overflow -= utilitiesReduction;
        context -= Math.min(overflow, context - LIMITS.context.min);
      }
      return { context: context, utilities: utilities };
    }

    function dynamicMaximum(side) {
      const other = side === "context" ? "utilities" : "context";
      return Math.max(
        LIMITS[side].min,
        Math.min(STORED_SIZE_LIMIT, availableForPanels() - applied[other])
      );
    }

    function updateSemantics() {
      Object.keys(handles).forEach(function (side) {
        const handle = handles[side];
        handle.setAttribute("aria-valuemin", String(LIMITS[side].min));
        handle.setAttribute("aria-valuemax", String(Math.round(dynamicMaximum(side))));
        handle.setAttribute("aria-valuenow", String(Math.round(applied[side])));
        handle.setAttribute("aria-valuetext", Math.round(applied[side]) + " pixels");
      });
    }

    function render(sizes) {
      applied = fitToViewport(sizes);
      layout.style.setProperty("--context-panel-size", applied.context + "px");
      layout.style.setProperty("--utilities-panel-size", applied.utilities + "px");
      updateSemantics();
    }

    function persist() {
      if (!storage) return;
      try {
        storage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            version: VERSION,
            context: Math.round(preferred.context),
            utilities: Math.round(preferred.utilities),
          })
        );
      } catch (_error) {
        // Resizing remains functional when browser storage is unavailable.
      }
    }

    function setSide(side, requested, shouldPersist) {
      const next = {
        context: applied.context,
        utilities: applied.utilities,
      };
      next[side] = clamp(requested, LIMITS[side].min, dynamicMaximum(side));
      preferred = next;
      render(next);
      if (shouldPersist) persist();
    }

    function wireHandle(side) {
      const handle = handles[side];
      handle.addEventListener("keydown", function (event) {
        if (!media.matches) return;
        let next = applied[side];
        const direction = side === "context" ? 1 : -1;
        if (event.key === "ArrowRight") next += KEYBOARD_STEP * direction;
        else if (event.key === "ArrowLeft") next -= KEYBOARD_STEP * direction;
        else if (event.key === "Home") next = LIMITS[side].min;
        else if (event.key === "End") next = dynamicMaximum(side);
        else return;
        event.preventDefault();
        setSide(side, next, true);
      });

      handle.addEventListener("pointerdown", function (event) {
        if (!media.matches || event.button !== 0) return;
        event.preventDefault();
        const startX = event.clientX;
        const startSize = applied[side];
        const direction = side === "context" ? 1 : -1;
        handle.classList.add("is-resizing");
        handle.setPointerCapture(event.pointerId);

        function move(moveEvent) {
          setSide(side, startSize + (moveEvent.clientX - startX) * direction, false);
        }

        function finish() {
          handle.classList.remove("is-resizing");
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", finish);
          handle.removeEventListener("pointercancel", finish);
          persist();
        }

        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", finish);
        handle.addEventListener("pointercancel", finish);
      });
    }

    wireHandle("context");
    wireHandle("utilities");
    reset.addEventListener("click", function () {
      preferred = defaults();
      render(preferred);
      if (storage) {
        try {
          storage.removeItem(STORAGE_KEY);
        } catch (_error) {
          // The visible reset still succeeds when storage is unavailable.
        }
      }
      if (status) status.textContent = "Panel sizes reset to defaults";
    });
    global.addEventListener("resize", function () {
      render(preferred);
    });

    render(preferred);
    return { getSizes: function () { return { context: applied.context, utilities: applied.utilities }; } };
  }

  global.PanelResizing = {
    init: init,
    storageKey: STORAGE_KEY,
  };

  if (global.document) init();
})(typeof globalThis !== "undefined" ? globalThis : this);
