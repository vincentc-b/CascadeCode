import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const staticDir = join(repoRoot, "cascade/war_room/static");

globalThis.marked = require(join(staticDir, "vendor/marked.min.js"));
const {
  findMermaidFences,
  rewriteWorkDocLinks,
  workIdFromDocHref,
  planHrefFromRelative,
  markdownToHtml,
  blockLineNumbersForBody,
  blockSourceRangesForBody,
  sectionSlug,
  sectionForSourceLine,
  lineRangeForSectionSlug,
  isSectionThread,
  findAnchorLineInRange,
  placementForRootThread,
  mermaidNodeHasDiagram,
  safeUrl,
} = require(join(staticDir, "plan_viewer.js"));

const slugVectors = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), "fixtures/section_slug_vectors.json"), "utf8")
);
for (const [heading, expected] of slugVectors) {
  assert.equal(sectionSlug(heading), expected);
  assert.doesNotMatch(expected, /_/);
}

const sampleMd = `# Plan

| A | B |
|---|---|
| 1 | 2 |

\`\`\`mermaid
flowchart LR
  X --> Y
\`\`\`

Plain \`code\`.
`;

const fences = findMermaidFences(sampleMd);
assert.equal(fences.length, 1);
assert.match(fences[0].content, /flowchart LR/);
assert.match(fences[0].content, /X --> Y/);

assert.equal(
  workIdFromDocHref("../../features/1_backlog/feat_012_plan_viewer.md"),
  "feat_012"
);
assert.equal(workIdFromDocHref("https://example.com/feat_001.md"), null);
assert.equal(
  planHrefFromRelative("../../tasks/1_backlog/task_057_plan_markdown_mermaid.md"),
  "/plan/task_057"
);

const linkHtml =
  '<p>See <a href="../../features/1_backlog/feat_012_plan_viewer.md">feat</a>.</p>';
const rewritten = rewriteWorkDocLinks(linkHtml);
assert.match(rewritten, /href="\/plan\/feat_012"/);
assert.doesNotMatch(rewritten, /feat_012_plan_viewer\.md/);

const jsLinkHtml = markdownToHtml("[click](javascript:alert(1))");
assert.doesNotMatch(jsLinkHtml, /href\s*=\s*["']?\s*javascript:/i);
assert.match(jsLinkHtml, /click/);

const dataLinkHtml = markdownToHtml("[x](data:text/html,<script>alert(1)</script>)");
assert.doesNotMatch(dataLinkHtml, /href\s*=\s*["']?\s*data:/i);

assert.equal(safeUrl("javascript:alert(1)"), null);
assert.equal(safeUrl("../../features/1_backlog/feat_012_plan_viewer.md"), "../../features/1_backlog/feat_012_plan_viewer.md");

const relLinkMd = "See [feat](../../features/1_backlog/feat_012_plan_viewer.md).";
const relLinkParsed = rewriteWorkDocLinks(markdownToHtml(relLinkMd));
assert.match(relLinkParsed, /href="\/plan\/feat_012"/);

const mermaidHtml = markdownToHtml("```mermaid\nflowchart LR\n  A --> B\n```");
assert.match(mermaidHtml, /class="mermaid"/);
assert.match(mermaidHtml, /flowchart LR/);

assert.deepEqual(blockLineNumbersForBody(sampleMd), [1, 3, 7, 12]);

const sampleHtml = markdownToHtml(sampleMd);
assert.match(sampleHtml, /<h1 data-src-line="1">Plan<\/h1>/);
assert.match(sampleHtml, /<table data-src-line="3">/);
assert.match(sampleHtml, /<div class="mermaid" data-src-line="7">/);
assert.match(sampleHtml, /<p data-src-line="12">Plain/);

assert.equal(mermaidNodeHasDiagram(null), false);
assert.equal(mermaidNodeHasDiagram({ querySelector: () => null }), false);
assert.equal(mermaidNodeHasDiagram({ querySelector: (sel) => (sel === "svg" ? {} : null) }), true);

const sectionDoc = "# Title\n\nIntro\n\n## Scope\n\nLine under scope.\n";
assert.equal(sectionForSourceLine(sectionDoc, 2), "title");
assert.equal(sectionForSourceLine(sectionDoc, 4), "title");
assert.equal(sectionForSourceLine(sectionDoc, 6), "scope");

const ranges = blockSourceRangesForBody("# H\n\nPara.");
assert.equal(ranges.length, 2);
assert.equal(ranges[0].lineStart, 1);
assert.equal(ranges[1].lineStart, 3);

const reanchorDoc = `# My Doc

Intro paragraph alpha.

## Scope

First line of scope.
Second line here.

## Other

Tail content.
`;

const scopeRange = lineRangeForSectionSlug(reanchorDoc, "scope");
assert.equal(scopeRange.startLine, 5);
assert.equal(scopeRange.endLine, 9);
assert.equal(isSectionThread(reanchorDoc, "scope"), true);
assert.equal(isSectionThread(reanchorDoc, "my-doc"), false);

assert.equal(findAnchorLineInRange(reanchorDoc, "Second line here", 5, 9), 8);
assert.equal(findAnchorLineInRange(reanchorDoc, "missing snippet", 5, 9), null);
assert.equal(findAnchorLineInRange(reanchorDoc, "Intro paragraph", 1, 5), 3);

const shaMatch = placementForRootThread(
  {
    id: "cmt_1",
    section: "scope",
    anchor: "gone",
    line_start: 8,
    doc_sha: "abc123",
  },
  reanchorDoc,
  "abc123"
);
assert.equal(shaMatch.outdated, false);
assert.equal(shaMatch.gutterLine, 8);

const sectionHit = placementForRootThread(
  {
    id: "cmt_2",
    section: "scope",
    anchor: "Second line here",
    line_start: 8,
    doc_sha: "old",
  },
  reanchorDoc,
  "new"
);
assert.equal(sectionHit.outdated, false);
assert.equal(sectionHit.gutterLine, 8);

const sectionMiss = placementForRootThread(
  {
    id: "cmt_3",
    section: "scope",
    anchor: "deleted text",
    line_start: 8,
    doc_sha: "old",
  },
  reanchorDoc,
  "new"
);
assert.equal(sectionMiss.outdated, true);
assert.equal(sectionMiss.gutterLine, 5);

const docHit = placementForRootThread(
  {
    id: "cmt_4",
    section: "general",
    anchor: "Intro paragraph alpha",
    line_start: 2,
    doc_sha: "old",
  },
  reanchorDoc,
  "new"
);
assert.equal(docHit.outdated, false);
assert.equal(docHit.gutterLine, 3);

const docMiss = placementForRootThread(
  {
    id: "cmt_5",
    section: "my-doc",
    anchor: "nowhere",
    line_start: 2,
    doc_sha: "old",
  },
  reanchorDoc,
  "new"
);
assert.equal(docMiss.outdated, true);
assert.equal(docMiss.gutterLine, 1);

console.log("plan_render cases ok");
