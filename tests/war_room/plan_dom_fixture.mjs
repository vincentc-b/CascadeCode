/**
 * Minimal DOM for plan_viewer initPlanComments regression cases (feat_019_001).
 */

function parseClasses(className) {
  return new Set(String(className || "").split(/\s+/).filter(Boolean));
}

function classListFor(el) {
  return {
    add(name) {
      const classes = parseClasses(el.className);
      classes.add(name);
      el.className = [...classes].join(" ");
    },
    remove(name) {
      const classes = parseClasses(el.className);
      classes.delete(name);
      el.className = [...classes].join(" ");
    },
    toggle(name, force) {
      const classes = parseClasses(el.className);
      const next = force !== undefined ? !!force : !classes.has(name);
      if (next) {
        classes.add(name);
      } else {
        classes.delete(name);
      }
      el.className = [...classes].join(" ");
    },
    contains(name) {
      return parseClasses(el.className).has(name);
    },
  };
}

function createElement(tag) {
  const el = {
    tagName: String(tag).toUpperCase(),
    nodeType: 1,
    className: "",
    id: "",
    textContent: "",
    hidden: false,
    disabled: false,
    type: "",
    name: "",
    rows: 0,
    value: "",
    children: [],
    parentNode: null,
    attributes: {},
    classList: null,
    childNodes: null,
    addEventListener() {},
    remove() {
      if (!el.parentNode) return;
      const idx = el.parentNode.children.indexOf(el);
      if (idx >= 0) {
        el.parentNode.children.splice(idx, 1);
      }
      el.parentNode = null;
    },
    appendChild(child) {
      if (child.parentNode) {
        child.remove();
      }
      el.children.push(child);
      child.parentNode = el;
      return child;
    },
    insertBefore(node, ref) {
      if (node.parentNode) {
        node.remove();
      }
      const idx = ref ? el.children.indexOf(ref) : el.children.length;
      if (idx < 0) {
        el.children.push(node);
      } else {
        el.children.splice(idx, 0, node);
      }
      node.parentNode = el;
      return node;
    },
    getAttribute(name) {
      return el.attributes[name] ?? null;
    },
    setAttribute(name, value) {
      el.attributes[name] = String(value);
    },
    removeAttribute(name) {
      delete el.attributes[name];
    },
    querySelector(sel) {
      const hits = querySelectorAll(el, sel);
      return hits.length ? hits[0] : null;
    },
    querySelectorAll(sel) {
      return querySelectorAll(el, sel);
    },
    contains(target) {
      if (target === el) return true;
      for (const child of el.children) {
        if (child === target || child.contains(target)) return true;
      }
      return false;
    },
    cloneNode(deep) {
      const copy = createElement(el.tagName.toLowerCase());
      copy.className = el.className;
      copy.id = el.id;
      copy.textContent = el.textContent;
      copy.hidden = el.hidden;
      copy.type = el.type;
      copy.name = el.name;
      copy.value = el.value;
      copy.attributes = { ...el.attributes };
      if (deep) {
        for (const child of el.children) {
          copy.appendChild(child.cloneNode(true));
        }
      }
      return copy;
    },
    focus() {},
  };

  Object.defineProperty(el, "innerHTML", {
    set() {
      el.children = [];
    },
    get() {
      return "";
    },
  });

  Object.defineProperty(el, "nextSibling", {
    get() {
      if (!el.parentNode) return null;
      const idx = el.parentNode.children.indexOf(el);
      return idx >= 0 && idx < el.parentNode.children.length - 1
        ? el.parentNode.children[idx + 1]
        : null;
    },
  });

  el.classList = classListFor(el);
  el.childNodes = el.children;
  return el;
}

function matchesSelector(el, selector) {
  if (!el || el.nodeType !== 1) return false;
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
    if (value === undefined) {
      return el.getAttribute(attr) != null;
    }
    return el.getAttribute(attr) === value;
  }
  if (/^[a-z0-9-]+$/i.test(trimmed)) {
    return el.tagName === trimmed.toUpperCase();
  }
  return false;
}

function querySelectorAll(root, selector) {
  const results = [];
  function walk(node) {
    if (node.nodeType === 1 && matchesSelector(node, selector)) {
      results.push(node);
    }
    for (const child of node.children || []) {
      walk(child);
    }
  }
  walk(root);
  return results;
}

function installPlanCommentDom() {
  const panel = createElement("section");
  panel.id = "plan-comments";
  const threadEl = createElement("div");
  threadEl.id = "plan-comment-threads";
  const compose = createElement("form");
  compose.id = "plan-comment-compose";
  const bodyInput = createElement("textarea");
  bodyInput.id = "plan-comment-body";
  const blockingInput = createElement("input");
  blockingInput.id = "plan-comment-blocking";
  blockingInput.type = "checkbox";
  const statusEl = createElement("p");
  statusEl.id = "plan-comment-status";
  statusEl.setAttribute("role", "status");
  const selectionBar = createElement("div");
  selectionBar.id = "plan-comment-selection-bar";
  selectionBar.hidden = true;
  const selectionBtn = createElement("button");
  selectionBtn.id = "plan-comment-on-selection";
  const composeHint = createElement("p");
  composeHint.id = "plan-comment-compose-hint";
  const bodyEl = createElement("div");
  bodyEl.id = "plan-body";

  panel.appendChild(threadEl);
  panel.appendChild(compose);
  compose.appendChild(bodyInput);
  compose.appendChild(blockingInput);
  compose.appendChild(statusEl);
  panel.appendChild(selectionBar);
  selectionBar.appendChild(selectionBtn);
  compose.appendChild(composeHint);

  const byId = {
    "plan-comments": panel,
    "plan-comment-threads": threadEl,
    "plan-comment-compose": compose,
    "plan-comment-body": bodyInput,
    "plan-comment-blocking": blockingInput,
    "plan-comment-status": statusEl,
    "plan-comment-selection-bar": selectionBar,
    "plan-comment-on-selection": selectionBtn,
    "plan-comment-compose-hint": composeHint,
    "plan-body": bodyEl,
  };

  globalThis.document = {
    getElementById(id) {
      return byId[id] || null;
    },
    createElement,
    body: createElement("body"),
  };

  globalThis.window = {
    getSelection() {
      return null;
    },
    scrollX: 0,
    scrollY: 0,
    scrollTo() {},
  };

  return { panel, threadEl, bodyEl, statusEl };
}

export { createElement, installPlanCommentDom, querySelectorAll };
