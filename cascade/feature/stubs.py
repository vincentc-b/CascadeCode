"""Feature tools stubbed until comment store (feat_005) and amendments (feat_006)."""

from __future__ import annotations


class FeatureToolUnavailable(Exception):
    """Feature tool not implemented in the current feature tier."""

    status_code = 501
