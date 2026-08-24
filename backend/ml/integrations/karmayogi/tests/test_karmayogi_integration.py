import os
import json
import tempfile
import time

from ml.integrations.karmayogi.taxonomy import get_taxonomy, CACHE_FILE
from ml.integrations.karmayogi.mapping import competency_id
from ml.integrations.karmayogi.oauth import generate_pkce_pair, build_authorize_url, client_credentials_token
from ml.integrations.karmayogi.client import KarmayogiClient


def test_pkce_generation_and_authorize_url():
    v, c = generate_pkce_pair(32)
    assert isinstance(v, str) and isinstance(c, str)
    # build_authorize_url should raise if no endpoint configured and none provided
    try:
        build_authorize_url("cid", "https://a/cb", code_challenge=c, auth_endpoint=None)
        raised = False
    except RuntimeError:
        raised = True
    assert raised


def test_mapping_falls_back_to_tag_when_no_taxonomy(monkeypatch):
    # Ensure taxonomy cache is absent
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    # No env mapping
    monkeypatch.delenv("KARMAYOGI_COMPETENCY_MAP", raising=False)
    tag = "policy-analysis"
    assert competency_id(tag) == tag


def test_taxonomy_cache_and_fetch(monkeypatch, tmp_path):
    # Simulate remote fetch by monkeypatching fetch function to return known list
    from ml.integrations.karmayogi import taxonomy as taxmod
    def fake_fetch():
        return [{"id": "C1", "name": "Policy Analysis", "tag": "policy-analysis"}]
    monkeypatch.setattr(taxmod, "fetch_taxonomy_from_remote", lambda: fake_fetch())
    # Remove any stale cache
    if os.path.exists(taxmod.CACHE_FILE):
        os.remove(taxmod.CACHE_FILE)
    tax = get_taxonomy(force_refresh=True)
    assert isinstance(tax, list) and len(tax) == 1
    # Now mapping should find id
    assert competency_id("policy-analysis") in ("C1", "Policy Analysis")


def test_client_list_courses_no_base_returns_empty():
    client = KarmayogiClient(base_url="")
    assert client.list_courses("x") == []


def test_post_progress_returns_false_when_no_base():
    client = KarmayogiClient(base_url="")
    assert client.post_progress("u1", "c1", 0.5) is False

# client_credentials_token will return None if env not configured; ensure it does
def test_client_credentials_token_no_env(monkeypatch):
    monkeypatch.delenv("KARMAYOGI_TOKEN_URL", raising=False)
    monkeypatch.delenv("KARMAYOGI_CLIENT_ID", raising=False)
    monkeypatch.delenv("KARMAYOGI_CLIENT_SECRET", raising=False)
    assert client_credentials_token() is None
