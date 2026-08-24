from .client import KarmayogiClient
from .mapping import competency_id


def ranked_courses(tag, learner_difficulty=0.5, limit=3):
    courses = KarmayogiClient().list_courses(competency_id(tag))
    ranked = []
    for course in courses:
        rating = float(course.get("rating", 0.5) or .5)
        course_difficulty = float(course.get("difficulty", learner_difficulty) or learner_difficulty)
        score = .45 + .30 * max(0, 1 - abs(course_difficulty - learner_difficulty)) + .25 * min(1, rating / 5)
        ranked.append((score, course))
    return [course for _, course in sorted(ranked, reverse=True, key=lambda item: item[0])[:limit]]
