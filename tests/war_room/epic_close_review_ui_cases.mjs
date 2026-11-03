import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const ui = require("../../cascade/war_room/static/epic_close_review_ui.js");

function element(tagName) {
  return {
    tagName,
    children: [],
    attributes: {},
    appendChild(child) { this.children.push(child); return child; },
    setAttribute(name, value) { this.attributes[name] = value; },
  };
}

const document = { createElement: element };

function render(review) {
  const row = element("div");
  const actions = element("div");
  let finishes = 0;
  ui.append(document, row, actions, review, {
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
    finishClose() { finishes += 1; },
  });
  return { row, actions, finishes: () => finishes };
}

{
  const result = render({
    close_stage: "implementation_review_pending",
    review_url: "https://forge.example/pull/17",
    forge_state: "<img src=x onerror=alert(1)>",
  });
  assert.equal(result.row.children[0].textContent, "Implementation review pending");
  assert.equal(result.row.children[0].attributes["aria-label"],
    "Epic close status: Implementation review pending");
  assert.equal(result.actions.children[0].textContent, "Open implementation review");
  assert.equal(result.actions.children[0].href, "https://forge.example/pull/17");
  assert.equal(result.actions.children[0].target, "_blank");
  assert.match(result.actions.children[0].rel, /noopener/);
  assert.equal(result.row.innerHTML, undefined);
}

{
  const hostile = "Restore forge access <script>alert(1)</script>, then retry.";
  const result = render({
    close_stage: "blocked",
    review_url: "https://forge.example/pull/17",
    blocker: { code: "review_lookup_failed", message: hostile, retryable: true },
  });
  assert.equal(result.row.children[1].textContent, hostile);
  assert.equal(result.row.children[1].innerHTML, undefined);
  const finish = result.actions.children.find((item) => item.textContent === "Finish close");
  assert.ok(finish);
  finish.callback();
  assert.equal(result.finishes(), 1);
}

{
  const result = render({ close_stage: "completed", review_url: null });
  assert.equal(result.row.children[0].textContent, "Close completed");
  assert.equal(result.actions.children.length, 0);
}
