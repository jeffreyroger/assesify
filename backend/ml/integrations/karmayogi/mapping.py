"""Canonical competency mapping; external IDs can be supplied by deployment.

This module first consults a simple environment-provided map (KARMAYOGI_COMPETENCY_MAP)
and otherwise consults the local taxonomy cache for a best-effort mapping.
"""
import os
import logging
from .taxonomy import get_taxonomy

LOG = logging.getLogger(__name__)


def _parse_env_map():
    raw = os.getenv("KARMAYOGI_COMPETENCY_MAP", "")
    mappings = {}
    for item in raw.split(","):
        if "=" in item:
            k, v = item.split("=", 1)
            mappings[k.strip().lower()] = v.strip()
    return mappings


def competency_id(tag: str) -> str:
    if not tag:
        return tag
    tag_norm = tag.strip().lower()
    env_map = _parse_env_map()
    if tag_norm in env_map:
        return env_map[tag_norm]

    # consult taxonomy: try to find an exact tag or name match
    try:
        taxonomy = get_taxonomy()
        for entry in taxonomy:
            # common fields: 'id', 'identifier', 'name', 'tag'
            name = (entry.get("name") or entry.get("title") or "").strip().lower()
            ident = str(entry.get("id") or entry.get("identifier") or "").strip()
            tag_field = (entry.get("tag") or entry.get("code") or "").strip().lower()
            if tag_norm == name or tag_norm == tag_field or tag_norm == ident:
                return ident or tag_norm
            # substring match
            if tag_norm in name:
                return ident or name
    except Exception as e:
        LOG.debug("Taxonomy lookup failed: %s", e)

    # default: return original tag
    return tag
