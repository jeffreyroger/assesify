"""Best-effort mastery event push; disabled until integration credentials exist."""
import json
import os
from urllib.request import Request, urlopen


def push_mastery_event(karmayogi_user_id, competency_tag, mastery):
    base_url = os.getenv("KARMAYOGI_BASE_URL", "").rstrip("/")
    if not base_url or not karmayogi_user_id:
        return False
    payload = json.dumps({"user_id": karmayogi_user_id, "competency": competency_tag, "mastery": mastery}).encode()
    request = Request(f"{base_url}/karmayogi/api/progress/v1/update", data=payload,
                      headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(request, timeout=4) as response:  # nosec B310 configured endpoint
            return 200 <= response.status < 300
    except Exception:
        return False
