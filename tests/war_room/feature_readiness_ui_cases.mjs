import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const FeatureReadinessUi = require(
  join(repoRoot, "cascade/war_room/static/feature_readiness_ui.js")
);

function createElement(tag) {
  return {
    tagName: tag.toUpperCase(),
    className: "",
    children: [],
    attributes: {},
    textContent: "",
    href: "",
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    setAttribute(name, value) {
      this.attributes[name] = value;
    },
    addEventListener() {},
  };
}

const document = {
  createElement,
  createTextNode(text) {
    return { tagName: "#TEXT", textContent: text, children: [] };
  },
};

function descendants(node) {
  return [node].concat((node.children || []).flatMap(descendants));
}

const readiness = {
  approved: true,
  explanation: {
    version: 1,
    summary: "waiting",
    primary_reason_code: "sibling_active_execution",
    reasons: [
      {
        code: "sibling_active_execution",
        message: "Another feature in this Epic is actively executing.",
        affected_work_ids: ["feat_034_009"],
        next_action: "Wait for the active sibling feature to finish execution.",
        links: [{ label: "Open feat_034_009 plan", href: "/plan/feat_034_009" }],
      },
      {
        code: "dependency_status_unavailable",
        message: "Dependency status is unavailable and is being rechecked.",
        affected_work_ids: ["feat_034_007"],
        links: [],
      },
    ],
    satisfied: [
      {
        code: "approval_current",
        message: "The feature is approved.",
        affected_work_ids: ["feat_034_008"],
      },
    ],
    last_dispatch_attempt: {
      at: "2026-11-13T12:00:00+00:00",
      outcome: "refused",
      historical: true,
      history_state: "changed_sources",
      detail: "Sibling was active.",
    },
  },
};

assert.equal(
  FeatureReadinessUi.summaryText(readiness.explanation),
  "Waiting — Another feature in this Epic is actively executing."
);

const rendered = FeatureReadinessUi.render(document, readiness, "feat_034_008");
assert.equal(rendered.tagName, "SECTION");
assert.equal(rendered.attributes["aria-label"], "Activation readiness for feat_034_008");

const nodes = descendants(rendered);
const details = nodes.find((node) => node.tagName === "DETAILS");
const summary = nodes.find((node) => node.tagName === "SUMMARY");
assert.ok(details, "details uses the browser's native disclosure behavior");
assert.equal(summary.attributes["aria-label"], "Show activation readiness details for feat_034_008");
assert.ok(nodes.some((node) => node.textContent.includes("Dependency status is unavailable")));
assert.ok(nodes.some((node) => node.textContent.includes("The feature is approved")));
assert.ok(nodes.some((node) => node.textContent.includes("Historical; readiness has changed")));

const link = nodes.find((node) => node.tagName === "A");
assert.equal(link.textContent, "Open feat_034_009 plan");
assert.equal(link.href, "/plan/feat_034_009");

const missingEvidence = FeatureReadinessUi.render(document, {
  explanation: {
    version: 1,
    summary: "unavailable",
    primary_reason_code: "provider_evidence_unavailable",
    reasons: [{ code: "provider_evidence_unavailable", message: "Provider evidence is missing.", links: [] }],
    satisfied: [],
    last_dispatch_attempt: null,
  },
}, "feat_002");
assert.ok(descendants(missingEvidence).some((node) =>
  node.textContent === "Readiness unavailable — Provider evidence is missing."
));

console.log("feature_readiness_ui_cases: ok");
