"""Competency taxonomy synchronization and caching for Karmayogi.

Provides a get_taxonomy() function that will attempt to fetch the canonical
competency taxonomy from Karmayogi and cache it locally for KARMAYOGI_COMPETENCY_CACHE_TTL seconds.

When unavailable the function degrades gracefully and returns an empty list.
"""
import json
import os
import time
import logging
from urllib.request import urlopen, Request
from urllib.error import URLError

LOG = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")), ".cache")
CACHE_FILE = os.path.join(CACHE_DIR, "karmayogi_taxonomy.json")
TTL = int(os.getenv("KARMAYOGI_COMPETENCY_CACHE_TTL", "86400"))  # default 24h


def _load_cache():
    try:
        if not os.path.exists(CACHE_FILE):
            return None
        mtime = os.path.getmtime(CACHE_FILE)
        if time.time() - mtime > TTL:
            return None
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as e:
        LOG.debug("Failed to read taxonomy cache: %s", e)
        return None


def _save_cache(data):
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    except Exception as e:
        LOG.debug("Failed to write taxonomy cache: %s", e)


def fetch_taxonomy_from_remote() -> list:
    base = os.getenv("KARMAYOGI_BASE_URL", "").rstrip("/")
    if not base:
        return []
    url = f"{base}/karmayogi/api/competency/v1/list"
    req = Request(url)
    try:
        with urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("utf-8")
            try:
                payload = json.loads(raw)
            except Exception:
                return []
            # Expect a list or 'competencies' key
            if isinstance(payload, list):
                return payload
            return payload.get("competencies", payload.get("result", []))
    except (URLError, Exception) as e:
        LOG.debug("Could not fetch taxonomy from Karmayogi: %s", e)
        return []


def get_taxonomy(force_refresh: bool = False) -> list:
    """Return the competency taxonomy (list). Uses cached copy when available.

    force_refresh=True will attempt a remote fetch even if cache is valid.
    """
    if not force_refresh:
        cached = _load_cache()
        if cached is not None:
            return cached

    remote = fetch_taxonomy_from_remote()
    if remote:
        _save_cache(remote)
        return remote
    # fallback to cache even if stale
    cached = _load_cache()
    return cached or []
