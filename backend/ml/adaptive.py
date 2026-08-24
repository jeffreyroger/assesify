"""Adaptive next-item selection for normalized quiz questions."""
from math import exp


def select_next_question(questions, answered_ids, competency_mastery):
    """Choose the unanswered item with greatest information near current mastery.

    A logistic item response curve is most informative when item difficulty is
    close to the learner's estimated ability.  The implementation is compact,
    deterministic, and works without a separate Bayesian service.
    """
    candidates = [question for question in questions if question.id not in answered_ids]
    if not candidates:
        return None

    def information(question):
        mastery = competency_mastery.get(question.competency_tag, 0.5)
        probability = 1 / (1 + exp(-4 * (mastery - question.difficulty)))
        return probability * (1 - probability)

    return max(candidates, key=information)
