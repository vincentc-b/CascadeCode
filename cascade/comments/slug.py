"""Hyphenated section slugs for comment threads (feat_016)."""

from __future__ import annotations

import re

_NON_SLUG = re.compile(r"[^a-z0-9]+")


def section_slug(heading: str) -> str:
    """GitHub-style slug: lowercase, non [a-z0-9] runs become a single hyphen."""

    slug = _NON_SLUG.sub("-", heading.strip().lower())
    return slug.strip("-")
