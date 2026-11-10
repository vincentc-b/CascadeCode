# Comment design

Purpose: store accountable, section-addressed review comments and route acknowledgements/escalations. Interfaces are the comment store, `Comment`, section slugs, and handoff/hold helpers. Owns `REQ-COMMENT-001` (comments retain accountable routing) and `DEC-COMMENT-001` (comment identity is durable outside chat).

Evidence: `cascade/comments/` and `tests/comments/` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory digest `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: unavailable review descriptions limit intent reconstruction.
