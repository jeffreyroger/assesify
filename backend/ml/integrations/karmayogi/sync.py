"""Best-effort mastery event push; uses KarmayogiClient when available."""
import json
import os
import logging

from .client import KarmayogiClient

LOG = logging.getLogger(__name__)


def push_mastery_event(karmayogi_user_id, competency_tag, mastery):
    """Push mastery event to Karmayogi using the client.

    Returns True on success, False otherwise. This function never raises for
    network errors and is safe to call in batch jobs.
    """
    base = os.getenv("KARMAYOGI_BASE_URL", "").rstrip("/")
    if not base or not karmayogi_user_id:
        return False
    try:
        client = KarmayogiClient(base_url=base)
        # If service account creds are present, attempt to set a token
        client_id = os.getenv("KARMAYOGI_CLIENT_ID")
        client_secret = os.getenv("KARMAYOGI_CLIENT_SECRET")
        if client_id and client_secret:
            # We don't implement credential exchange here; if a token provider exists
            # set_token can be called by the application with the token.
            pass
        return client.post_progress(karmayogi_user_id, competency_tag, mastery)
    except Exception as e:
        LOG.debug("push_mastery_event failed: %s", e)
        return False
