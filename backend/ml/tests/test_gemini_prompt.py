from ml.gemini_prompt import build_personalized_mcq_prompt


def test_personalized_prompt_contains_fields():
    p = build_personalized_mcq_prompt("algebra", "linear_equations", "Solve for x", difficulty="easy", weaknesses=["fractions"], n_questions=3)
    assert "Topic: algebra" in p
    assert "Subtopic: linear_equations" in p
    assert "Learning objective: Solve for x" in p
    assert "Student weaknesses" in p
    assert "Number of questions: 3" in p
