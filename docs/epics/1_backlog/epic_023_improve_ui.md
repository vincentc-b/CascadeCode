---
id: epic_023
title: Improve UI
tier: epic
status: backlog
parent: null
children: []
depends_on: []
owners:
- epic_manager
- epic_architect
skills: []
parent_rev: null
created: '2026-10-23'
updated: '2026-10-23'
provider: codex
models:
  epic_manager: gpt-5.6-sol
  epic_architect: gpt-5.6-sol
---
# Improve UI

## Intent

The current UI is flaky. The board width varies and changes without command and the layout can be somewhat clunky. I think the board should be at the center, and the current center column with teh "in flight", chat, etc should go to the left side. We should be able to adjust the width of each column to take advantage of the full screen size and different screen sizes. Also, it would be great to allow backlog items to be drag/dropped to prioritize them. The UI should perform very well with low latency, a dedicated performance review effort would be welcome.

### Success criteria

-Main board is centered, feature context and chat move left.
-Features in backlog can be re-ordered for priorities
-UI "columns" can be resized
-UI supports multiple screen sizes
-Changes in state reflect quickly, and the page loads quickly (<2s)

## Macro-architecture

To be developed by the Epic Manager and Epic Architect after activation.

## Cross-module constraints

To be refined by the Epic Team during planning.

## Core dependencies

To be identified during epic planning.

## Feature breakdown

The Epic Team will create and sequence feature plans here.

## Open questions

- Which implementation risks should be resolved before the first feature starts?

## Decision log

- 2026-10-23 · Human · Brief approved through merge request review.

## Amendment log

_(none)_
