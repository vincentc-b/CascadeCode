import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { createElement } from "./plan_dom_fixture.mjs";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const DependencyReviewUi = require(
  join(repoRoot, "cascade/war_room/static/dependency_review_ui.js")
);
const PlanViewer = require(join(repoRoot, "cascade/war_room/static/plan_viewer.js"));

function enhancedElement(tag) {
  const el = createElement(tag);
  const listeners = new Map();
  el.addEventListener = (type, handler) => {
    if (!listeners.has(type)) listeners.set(type, []);
    listeners.get(type).push(handler);
  };
  el.dispatch = (type) => {
    for (const handler of listeners.get(type) || []) {
      handler({ type, stopPropagation() {} });
    }
  };
  el.replaceChildren = (...children) => {
    el.children = [];
    for (const child of children) el.appendChild(child);
  };
  return el;
}

const document = { createElement: enhancedElement };

function descendants(root) {
  const rows = [];
  function visit(node) {
    rows.push(node);
    for (const child of node.children || []) visit(child);
  }
  visit(root);
  return rows;
}

function byText(root, tag, text) {
  return descendants(root).find(
    (node) => node.tagName === tag.toUpperCase() && node.textContent === text
  );
}

function tick() {
  return new Promise((resolve) => setImmediate(resolve));
}

const hostileOutput = "failed <script>globalThis.compromised = true</script>\nrm -rf /not-run";
const binding = {
  dependency_id: "dep_tool",
  version: "1.2.3",
  source: "https://tool.example/releases/1.2.3.tgz",
  digest: "sha256:fixed",
  target_environment: {
    environment_id: "ci-container",
    kind: "container",
    os: "linux",
    architecture: "x86_64",
  },
  install_scope: "project-local",
  install_destination: ".tools/tool",
  operation: "install exact tool archive into .tools/tool",
  cleanup_plan: "remove .tools/tool",
};

const projection = {
  epic_id: "epic_001",
  status: "dependency_blocked",
  responsible_actor: "human",
  explicit_no_dependencies: false,
  manifest: { revision: 4 },
  bootstrap: {
    state: "awaiting_authorization",
    revision: 2,
    scope_manifest_revision: 4,
    scope_current: true,
    scope_fingerprint: "scope-fingerprint",
    scope: {
      manifest_revision: 4,
      entries: [{ dependency_id: "dep_tool", setup_operation: binding.operation }],
      feasibility_artifacts: [{ artifact_id: "probe" }],
    },
    authorization_state: "missing",
    projection_blockers: ["Human feasibility review is required."],
  },
  dependencies: [
    {
      dependency_id: "dep_tool",
      status: "blocked",
      responsible_actor: "human",
      binding,
      why_needed: ["render architecture"],
      actual_environment: {
        environment_id: "host",
        kind: "host",
        os: "linux",
        architecture: "x86_64",
      },
      environment_matches_target: false,
      last_check: {
        admitted_at: "2026-11-07T01:00:00+00:00",
        completed_at: "2026-11-07T01:00:01+00:00",
        operation: "tool --version",
        result: "failed",
        redacted_output: hostileOutput,
      },
      evidence: {
        state: "failed",
        failure: hostileOutput,
        next_action: "Install only the reviewed project-local archive, then ping the team.",
      },
      guidance: {
        investigation: "tool --version",
        setup: binding.operation,
        verification_operation: ".tools/tool --version",
        expected_verification: "tool 1.2.3",
        owned_artifact_cleanup: binding.cleanup_plan,
      },
      installation_approval: { state: "missing", current: [], stale: [] },
    },
  ],
  planning_readiness: {
    status: "planning",
    can_approve_plan: false,
    approve_disabled_reason: "dependency_evidence_not_ready",
  },
  errors: [],
};

const calls = [];
const host = enhancedElement("section");
DependencyReviewUi.renderInto(document, host, projection, {
  post(path, payload) {
    calls.push({ path, payload });
    if (path === "/api/approve_dependency_installations") {
      const current = structuredClone(projection);
      current.dependencies[0].installation_approval = {
        state: "current",
        current: [{
          approval_id: "approval-1",
          approver_id: "operator@example.test",
          approved_at: "2026-11-07T02:00:00+00:00",
        }],
        stale: [],
      };
      return Promise.resolve({ dependency_status: current });
    }
    return Promise.resolve({ dependency_status: projection });
  },
});

assert.equal(byText(host, "dd", "1.2.3").textContent, "1.2.3");
assert.ok(byText(host, "dd", ".tools/tool"), "complete binding includes destination");
assert.ok(byText(host, "dd", "No") || byText(host, "dd", "No"));
assert.ok(
  descendants(host).some((node) => node.textContent === hostileOutput),
  "redacted output remains visible as text"
);
assert.equal(descendants(host).some((node) => node.tagName === "SCRIPT"), false);
assert.equal(globalThis.compromised, undefined);
assert.ok(byText(host, "button", "Review bootstrap scope"));
assert.ok(byText(host, "button", "Retry verification"));

const approve = byText(host, "button", "Approve selected installations");
assert.ok(approve);
approve.dispatch("click");
await tick();
await tick();
assert.equal(calls[0].path, "/api/approve_dependency_installations");
assert.equal(calls[0].payload.manifest_revision, 4);
assert.deepEqual(calls[0].payload.entries, [
  { dependency_id: "dep_tool", binding },
]);
assert.ok(byText(host, "p", "Dependency state refreshed."));
assert.ok(
  descendants(host).some((node) =>
    String(node.textContent).includes("Current approval approval-1 by operator@example.test")
  )
);

const refusalHost = enhancedElement("section");
DependencyReviewUi.renderInto(document, refusalHost, projection, {
  post(_path, _payload) {
    const error = new Error("stale bootstrap scope");
    error.body = {
      refusal: { code: "stale_bootstrap_scope", detail: "Refresh and review the current scope." },
      dependency_status: projection,
    };
    return Promise.reject(error);
  },
});
const review = byText(refusalHost, "button", "Review bootstrap scope");
review.dispatch("click");
assert.ok(byText(refusalHost, "p", "Reviewing bootstrap scope…"), "pending feedback is visible");
await tick();
await tick();
assert.ok(byText(refusalHost, "p", "Refresh and review the current scope."));

const pingCalls = [];
const pingHost = enhancedElement("section");
DependencyReviewUi.renderInto(document, pingHost, projection, {
  post(path, payload) {
    pingCalls.push({ path, payload });
    return Promise.resolve({ dependency_status: projection });
  },
});
byText(pingHost, "button", "Retry verification").dispatch("click");
await tick();
await tick();
byText(pingHost, "button", "Retry verification").dispatch("click");
await tick();
await tick();
assert.equal(pingCalls[0].path, "/api/ping_dependency_team");
assert.equal(pingCalls[0].payload.request_id, pingCalls[1].payload.request_id);
assert.deepEqual(pingCalls[0].payload.approval_references, {});

const noDependencies = enhancedElement("section");
DependencyReviewUi.renderInto(document, noDependencies, {
  epic_id: "epic_002",
  status: "ready",
  explicit_no_dependencies: true,
  dependencies: [],
  errors: [],
  planning_readiness: { status: "ready_for_review", can_approve_plan: true },
});
assert.ok(
  descendants(noDependencies).some((node) =>
    String(node.textContent).includes("No software dependencies are required")
  )
);
assert.equal(byText(noDependencies, "button", "Retry verification"), undefined);

const planHost = enhancedElement("div");
planHost.hidden = true;
globalThis.document = {
  createElement: enhancedElement,
  getElementById(id) {
    return id === "dependency-review-host" ? planHost : null;
  },
};
const planPanel = PlanViewer.initDependencyReviewChrome(
  "epic_001",
  projection,
  null,
  { DependencyReviewUi }
);
assert.ok(planPanel, "plan view mounts the shared canonical panel");
assert.equal(planHost.hidden, false);
assert.equal(planHost.getAttribute("aria-label"), "Software dependency review for epic_001");

const missingDeclaration = enhancedElement("section");
DependencyReviewUi.renderInto(document, missingDeclaration, {
  epic_id: "epic_001", status: "blocked", manifest: null,
  errors: [{ code: "missing_manifest", detail: "Declaration required" }],
  dependencies: [],
  // Even a stale bootstrap projection must not expose controls before declaration.
  bootstrap: projection.bootstrap,
});
assert.ok(descendants(missingDeclaration).some((node) =>
  String(node.textContent).includes("Epic Manager or Architect must declare dependencies first")
));
assert.ok(descendants(missingDeclaration).some((node) =>
  String(node.textContent).includes("read_dependency_manifest and write_dependency_manifest")
));
assert.equal(descendants(missingDeclaration).filter((node) => node.tagName === "BUTTON").length, 0);

console.log("dependency_review_ui_cases: ok");

const verifiedHost = enhancedElement("section");
DependencyReviewUi.renderInto(document, verifiedHost, {
  ...projection,
  status: "ready",
  bootstrap: { ...projection.bootstrap, scope: { entries: [], feasibility_artifacts: [] } },
  dependencies: projection.dependencies.map(row => ({ ...row, status: "ready", installation_approval: { state: "missing", current: [] } })),
});
assert.ok(byText(verifiedHost, "span", "Installation approval: not needed (already verified)"));
assert.equal(byText(verifiedHost, "button", "Approve selected installations"), undefined);
assert.equal(byText(verifiedHost, "button", "Review bootstrap scope"), undefined);
