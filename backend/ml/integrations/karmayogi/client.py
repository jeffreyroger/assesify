"""Karmayogi REST client with bounded retry, optional auth token, and a cooldown.

This client is intentionally lightweight and dependency-free (urllib) so it can
be used in environments without external HTTP libraries. It supports an
optional bearer token (e.g., obtained via client-credentials or PKCE) by calling
`set_token()`.
"""
import json
import os
import time
import logging
from urllib.error import URLError, HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOG = logging.getLogger(__name__)


class KarmayogiClient:
    def __init__(self, base_url=None, timeout=4, max_retries: int = 3):
        self.base_url = (base_url or os.getenv("KARMAYOGI_BASE_URL", "")).rstrip("/")
        self.timeout = timeout
        self._unavailable_until = 0
        self._token = None
        self.max_retries = max_retries

    def set_token(self, token: str):
        """Set a bearer token to be sent with requests."""
        self._token = token

    def _build_request(self, path: str, method: str = "GET", data: bytes | None = None, headers: dict | None = None):
        url = f"{self.base_url}{path}"
        headers = headers.copy() if headers else {}
        headers.setdefault("Accept", "application/json")
        if data is not None:
            headers.setdefault("Content-Type", "application/json")
        if self._token:
            headers.setdefault("Authorization", f"Bearer {self._token}")
        return Request(url, data=data, headers=headers, method=method)

    def _perform_request(self, request: Request):
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                with urlopen(request, timeout=self.timeout) as response:  # nosec B310 configured endpoint
                    status = getattr(response, "status", None) or getattr(response, "getcode", lambda: None)()
                    raw = response.read().decode("utf-8")
                    try:
                        payload = json.loads(raw) if raw else {}
                    except Exception:
                        payload = raw
                    if 200 <= status < 300:
                        return payload
                    else:
                        LOG.warning("Karmayogi returned non-2xx status %s: %s", status, raw)
                        last_exc = HTTPError(request.full_url, status, "Non-2xx", hdrs=None, fp=None)
            except (URLError, HTTPError, TimeoutError) as e:
                last_exc = e
                # exponential-ish backoff
                sleep = 0.2 * (2 ** attempt)
                time.sleep(sleep)
                continue
        # enter cooldown on repeated failures
        self._unavailable_until = time.time() + 30
        LOG.error("Karmayogi client unavailable until %s due to: %s", self._unavailable_until, last_exc)
        raise last_exc

    def list_courses(self, competency):
        if not self.base_url or time.time() < self._unavailable_until:
            return []
        query = urlencode({"competency": competency})
        path = f"/karmayogi/api/course/v1/list?{query}"
        req = self._build_request(path)
        try:
            data = self._perform_request(req)
            return data.get("courses", data.get("result", data if isinstance(data, list) else []))
        except Exception:
            return []

    def post_progress(self, karmayogi_user_id: str, competency: str, mastery: float):
        """Post a progress update event to Karmayogi. Returns True on success.

        This is best-effort and will return False if the client is not configured
        or the call fails. Does not raise unless a critical internal error occurs.
        """
        if not self.base_url or not karmayogi_user_id:
            return False
        path = "/karmayogi/api/progress/v1/update"
        payload = json.dumps({"user_id": karmayogi_user_id, "competency": competency, "mastery": mastery}).encode(
            "utf-8"
        )
        req = self._build_request(path, method="POST", data=payload, headers={"Content-Type": "application/json"})
        try:
            self._perform_request(req)
            return True
        except Exception:
            return False
