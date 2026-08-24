"""Karmayogi catalog integration with a safe internal-quiz fallback."""
import json
import os
from base64 import b64encode
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from app.models.lesson import Lesson
from ml.integrations.karmayogi.recommender import ranked_courses


def recommend_for_gap(competency_tag: str, limit: int = 3):
    ranked = ranked_courses(competency_tag, limit=limit)
    if ranked:
        return [{
            "course_id": str(course.get("id", course.get("identifier", ""))),
            "title": course.get("title", course.get("name", competency_tag)),
            "url": course.get("url", course.get("deepLink")),
            "score": float(course.get("rating", 0.5) or .5),
            "reason": f"Aligned to your {competency_tag} competency gap.",
            "source": "karmayogi",
        } for course in ranked]
    base_url = os.getenv("KARMAYOGI_BASE_URL", "").rstrip("/")
    if not base_url:
        return _internal_fallback(competency_tag)
    try:
        query = urlencode({"competency": competency_tag})
        request = Request(f"{base_url}/karmayogi/api/course/v1/list?{query}")
        client_id = os.getenv("KARMAYOGI_CLIENT_ID")
        client_secret = os.getenv("KARMAYOGI_CLIENT_SECRET")
        if client_id and client_secret:
            credentials = b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")
            request.add_header("Authorization", f"Basic {credentials}")
        with urlopen(request, timeout=4) as response:  # nosec B310 - configured service endpoint
            payload = json.loads(response.read().decode("utf-8"))
        courses = payload.get("courses", payload.get("result", payload if isinstance(payload, list) else []))
        return [
            {
                "course_id": str(course.get("id", course.get("identifier", ""))),
                "title": course.get("title", course.get("name", competency_tag)),
                "url": course.get("url", course.get("deepLink")),
                "score": round(float(course.get("rating", 0.5)), 3),
                "reason": f"Aligned to your {competency_tag} competency gap.",
                "source": "karmayogi",
            }
            for course in courses[:limit]
        ] or _internal_fallback(competency_tag)
    except Exception:
        return _internal_fallback(competency_tag)


def _internal_fallback(competency_tag: str):
    lesson = Lesson.query.filter(Lesson.topic.ilike(competency_tag)).first()
    return [{
        "course_id": None,
        "title": f"Practice: {lesson.title}" if lesson else f"Remedial practice: {competency_tag}",
        "url": f"/learn?topic={competency_tag}",
        "score": 1.0,
        "reason": "Karmayogi is unavailable; continue with an internal remedial quiz.",
        "source": "internal",
        "karmayogi_available": False,
    }]
