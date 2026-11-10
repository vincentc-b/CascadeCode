# Cascade package design

Purpose: expose the Python package and CLI composition root for repository-local delivery. Interfaces are `cascade.cli` and the domain packages below. Owns `REQ-CASCADE-001` (one local composition root) and `DEC-CASCADE-001` (domain packages remain independently testable).

Evidence: `cascade/cli.py`, `cascade/__init__.py`, and `tests/test_cli.py` at baseline `d932f48764cc0ceb2f4810cdd4487bef0c9ef084`; inventory SHA-256 `d86a5977ca42a2fd7da1ca80dc7b3251a8522f1a427e836c0abed741a816f1b6`.

Known gaps: missing receipts and unavailable reviews in the pinned inventory prevent complete historical attribution.
