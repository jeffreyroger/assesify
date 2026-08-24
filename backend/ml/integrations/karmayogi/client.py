"""Karmayogi REST client with bounded retry and a failure cooldown."""
import json
import os
import time
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class KarmayogiClient:
    def __init__(self, base_url=None, timeout=4):
        self.base_url = (base_url or os.getenv("KARMAYOGI_BASE_URL", "")).rstrip("/")
        self.timeout = timeout
        self._unavailable_until = 0

    def list_courses(self, competency):
        if not self.base_url or time.time() < self._unavailable_until:
            return []
        request = Request(f"{self.base_url}/karmayogi/api/course/v1/list?{urlencode({'competency': competency})}")
        for _ in range(3):
            try:
                with urlopen(request, timeout=self.timeout) as response:  # nosec B310 configured endpoint
                    data = json.loads(response.read().decode("utf-8"))
                return data.get("courses", data.get("result", data if isinstance(data, list) else []))
            except (URLError, TimeoutError, ValueError):
                time.sleep(0.2)
        self._unavailable_until = time.time() + 30
        return []
