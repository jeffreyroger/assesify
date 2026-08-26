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


def legacy_shape_from_questions(question_rows, include_answers=False):
    """Convert relational `Question` rows back into the legacy generator-dict
    shape (`id`/`question`/`options`/`hint`, plus `correct_answer`/`answer`
    only when `include_answers`) so old frontend consumers of
    `Quiz.to_dict()["questions"]` keep working unchanged regardless of whether
    the quiz was generated via the legacy or relational write path.

    `include_answers` defaults to **False** (spec §4.3 "Full quiz (teacher view)
    or sanitized (student)", §8 authz): a student must never receive the
    correct answer for a question they have not answered yet. Students obtain
    per-question feedback from
    `POST /api/quizzes/<quiz_id>/questions/<question_id>/check` *after*
    committing a selection. Teachers who own the quiz's lesson get the
    unredacted shape.
    """
    result = []
    for question in question_rows:
        options = question.options or []
        option_texts = [option.get("text") for option in options]
        item = {
            # Relational id, exposed so clients can identify the question when
            # autosaving a response, asking for feedback, or submitting the
            # quiz. Everything else in this dict is the historical legacy shape.
            "id": question.id,
            "question": question.stem,
            "options": option_texts,
            "hint": "",
        }
        if include_answers:
            correct_keys = question.correct_keys or []
            correct_text = None
            for option in options:
                if option.get("key") in correct_keys:
                    correct_text = option.get("text")
                    break
            item["correct_answer"] = correct_text
            item["answer"] = question.explanation
        result.append(item)
    return result


#: Keys of the legacy question shape that reveal the answer to the student.
REVEALING_LEGACY_KEYS = ("correct_answer", "answer")


def redact_legacy_blob(items):
    """Strip answer-revealing keys from deprecated `Quiz.questions` blob items.

    Only reachable for quizzes that predate the relational `Question` rows and
    were never backfilled; kept so the redaction invariant holds for *every*
    read path rather than only the relational one.
    """
    redacted = []
    for item in items or []:
        if isinstance(item, dict):
            redacted.append({k: v for k, v in item.items() if k not in REVEALING_LEGACY_KEYS})
        else:
            redacted.append(item)
    return redacted
