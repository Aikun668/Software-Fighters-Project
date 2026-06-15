"""Shared node ID normalization — avoids circular imports between graph_service and
knowledge_extraction."""

import re


def normalize_node_id(raw_id: str) -> str:
    """Normalize a raw node ID to lowercase alphanumeric + underscore + hyphen.

    Raises ValueError if the result would be empty.
    """
    normalized = re.sub(r"[^a-z0-9_\-]", "", raw_id.lower())
    if not normalized:
        raise ValueError("node id cannot be empty after normalization")
    return normalized
