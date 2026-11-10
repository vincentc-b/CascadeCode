# Board design

Purpose: make Markdown work documents and directory columns canonical lifecycle state. Interfaces are `WorkDoc`/`WorkMeta`, parse/validate, board stores, moves, indexing, and hierarchical ID allocation. Owns `REQ-BOARD-001` (filesystem state is authoritative) and `DEC-BOARD-001` (folder/frontmatter mismatches fail closed).

Evidence: `cascade/board/{types,parse,validate,store,work_ids}.py` and `tests/board/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: missing receipts prevent attributing every invariant to accepted work.

## Safe frontmatter scan performance

Worktree board scans may read thousands of records during a cold War Room request.
Use the available libyaml `CSafeLoader`, falling back to Python `SafeLoader`, with
unchanged schema parsing and safe-constructor restrictions. No loader may construct
Python objects from a work document. Existing file identity/mtime caches remain
unchanged, and mutations still validate current authoritative state. Tests exercise
both loaders, round trips and rejection of unsafe tags.
