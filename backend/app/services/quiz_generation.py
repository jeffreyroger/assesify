"""Shared helper for persisting generated quiz questions as relational rows.

Historically several call sites (legacy `/teacher/materials`, `/lessons/:id/quiz`,
the spec-compliant `/materials/:id/generate-quiz`) each wrote their own copy of
the "raw generator dict -> Question row" mapping, and some of them additionally
stuffed the raw list into `Quiz.questions` (a JSON blob column). This module is
the single place that performs that mapping so every writer produces the same
relational `Question` rows that attempts/scoring/mastery/adaptive-selection
already rely on.
"""
from app.models.assessment import Question
from app.models.users import db

DIFFICULTY_SCORES = {"easy": 0.3, "medium": 0.5, "hard": 0.8}


def persist_quiz_questions(quiz_id, questions, competency_tag="general", difficulty_name="medium"):
    """Create `Question` rows for `quiz_id` from a list of generator-shaped dicts.

    Each item is expected to look like the output of `ml.train.quiz_gen.generate_quiz`:
    `{"question": str, "options": [str, ...], "correct_answer": str, "answer": str}`.
    Returns the list of created (not yet committed) `Question` objects.
    """
    difficulty = DIFFICULTY_SCORES.get(difficulty_name, 0.5)
    rows = []
    for item in questions:
        options = item.get("options", [])
        correct = item.get("correct_answer")
        option_rows = [{"key": chr(65 + i), "text": value} for i, value in enumerate(options)]
        correct_keys = [row["key"] for row in option_rows if row["text"] == correct]
        if not correct_keys and option_rows:
            correct_keys = ["A"]
        row = Question(
            quiz_id=quiz_id,
            stem=item.get("question", ""),
            qtype="mcq",
            options=option_rows,
            correct_keys=correct_keys,
            explanation=item.get("answer"),
            difficulty=difficulty,
            competency_tag=competency_tag,
        )
        db.session.add(row)
        rows.append(row)
    return rows


def legacy_shape_from_questions(question_rows):
    """Convert relational `Question` rows back into the legacy generator-dict
    shape (`question`/`options`/`correct_answer`/`answer`/`hint`) so old
    frontend consumers of `Quiz.to_dict()["questions"]` keep working unchanged
    regardless of whether the quiz was generated via the legacy or relational
    write path.
    """
    result = []
    for question in question_rows:
        options = question.options or []
        option_texts = [option.get("text") for option in options]
        correct_keys = question.correct_keys or []
        correct_text = None
        for option in options:
            if option.get("key") in correct_keys:
                correct_text = option.get("text")
                break
        result.append({
            "question": question.stem,
            "options": option_texts,
            "correct_answer": correct_text,
            "answer": question.explanation,
            "hint": "",
        })
    return result
