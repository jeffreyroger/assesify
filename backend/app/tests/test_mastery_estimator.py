from app.services.irt import fit_theta_rasch, _sigmoid


def test_fit_theta_rasch_all_correct():
    # All correct answers should lead to high theta and mastery near 1.0
    diffs = [0.2, 0.5, 0.7, 0.4]
    outcomes = [1, 1, 1, 1]
    theta = fit_theta_rasch(diffs, outcomes, reg=0.1)
    mastery = _sigmoid(theta)
    assert mastery > 0.8


def test_fit_theta_rasch_all_wrong():
    # All incorrect answers should lead to low theta and mastery near 0.0
    diffs = [0.2, 0.5, 0.7, 0.4]
    outcomes = [0, 0, 0, 0]
    theta = fit_theta_rasch(diffs, outcomes, reg=0.1)
    mastery = _sigmoid(theta)
    assert mastery < 0.2


def test_fit_theta_rasch_mixed_responses_improves():
    # More correct responses should increase mastery
    diffs = [0.3, 0.6, 0.5, 0.4, 0.7]
    outcomes_a = [1, 0, 0, 0, 0]
    outcomes_b = [1, 1, 0, 0, 0]
    theta_a = fit_theta_rasch(diffs, outcomes_a, reg=0.1)
    theta_b = fit_theta_rasch(diffs, outcomes_b, reg=0.1)
    assert theta_b > theta_a
