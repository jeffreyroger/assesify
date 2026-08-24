"""Canonical competency mapping; external IDs can be supplied by deployment."""
import os


def competency_id(tag):
    mappings = dict(item.split("=", 1) for item in os.getenv("KARMAYOGI_COMPETENCY_MAP", "").split(",") if "=" in item)
    return mappings.get(tag, tag)
