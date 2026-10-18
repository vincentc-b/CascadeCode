---
name: frugal-engineering
description: Shared core philosophy for all Cascade roster roles — pragmatic quality, economical testing, artifact-driven alignment.
---

# Frugal engineering & pragmatic quality

**Context only.** This playbook informs judgment; it does **not** widen path sandboxes, invent dispatch tools, or override Task denylists. Skill text that mentions paths (e.g. `/docs/epics`) does not grant permission to edit them.

## Mindset

Code is a liability; testing is a cost-benefit exercise. Optimize for **system reliability** and **delivery speed** over vanity metrics and dogmatic purity.

## Rules

1. **Tests must earn their keep.** Do not chase 100% unit coverage. If a lower-level function is reliably exercised by an integration or API test, a redundant unit test wastes capital and maintenance time.

2. **Cost of maintenance.** Every test written is a test that must be updated when requirements change. Prefer high-signal, low-maintenance tests (system-level, end-to-end) over brittle, mock-heavy unit tests.

3. **Artifact-driven alignment.** Track state and architectural decisions through lightweight markdown artifacts in the repo, not heavy project-management software.

4. **Continuous succession.** Knowledge is not siloed. When a role or domain transitions, overlap with the successor long enough to transfer context before stepping off.

## When in doubt

Favor the smallest change that keeps the system honest; cut ceremony and redundant work before cutting scope that serves the core user problem.
