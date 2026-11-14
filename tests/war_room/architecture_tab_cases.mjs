import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const { applyLinkState, documentationContextUrl, linkState, sortedChoices } = require(
  join(repoRoot, "cascade/war_room/static/architecture_tab.js")
);

const snapshot = `architecture-snapshot-${"a".repeat(64)}`;
const deepLink = applyLinkState("https://example.test/?unrelated=kept", {
  tab: "architecture",
  context: "context-one",
  snapshot,
  view: "payments",
  level: "containerViews",
  target: "container.payments.api",
});
assert.equal(
  deepLink,
  `/?unrelated=kept&tab=architecture&context=context-one&snapshot=${snapshot}` +
    "&view=payments&level=containerViews&target=container.payments.api"
);

assert.equal(
  documentationContextUrl(snapshot, { key: "payments", level: "containerViews" }, null),
  `/api/architecture/snapshots/${snapshot}/context?view=payments&level=containerViews&kind=view`,
  "view context is bound to the opaque snapshot and verified view identity"
);
assert.equal(
  documentationContextUrl(
    snapshot,
    { key: "payments", level: "containerViews" },
    { kind: "relationship", semantic_id: "api calls ledger" }
  ),
  `/api/architecture/snapshots/${snapshot}/context?view=payments&level=containerViews` +
    "&kind=relationship&target=api+calls+ledger",
  "target context does not accept repository paths or revisions"
);
assert.deepEqual(linkState(deepLink.split("?", 2)[1]), {
  tab: "architecture",
  context: "context-one",
  snapshot,
  view: "payments",
  level: "containerViews",
  target: "container.payments.api",
});

assert.deepEqual(
  sortedChoices({ drill_choices: [
    { view_key: "zeta", level: "componentViews", label: "Zeta" },
    { view_key: "beta", level: "containerViews", label: "Beta" },
    { view_key: "alpha", level: "containerViews", label: "Alpha" },
  ] }).map((row) => row.view_key),
  ["alpha", "beta", "zeta"],
  "drill destinations are stable by C4 level and key"
);

assert.equal(
  applyLinkState(deepLink, {
    tab: "board", context: null, snapshot: null, view: null, level: null, target: null,
  }),
  "/?unrelated=kept",
  "clearing architecture navigation retains unrelated query state"
);
