"""IRT / Rasch utilities (kept independent of Flask/SQLAlchemy to ease unit testing).

Provides:
- _sigmoid(x)
- _logit(p)
- fit_theta_rasch(difficulties, outcomes, ...)

These are pure functions with no DB dependencies so they can be unit-tested in isolation.
"""
from typing import Iterable


def _sigmoid(x: float) -> float:
    import math

    try:
        if x >= 0:
            z = math.exp(-x)
            return 1.0 / (1.0 + z)
        else:
            z = math.exp(x)
            return z / (1.0 + z)
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def _logit(p: float) -> float:
    import math

    eps = 1e-6
    p = min(max(p, eps), 1 - eps)
    return math.log(p / (1 - p))


def fit_theta_rasch(difficulties: Iterable[float], outcomes: Iterable[int], reg: float = 1.0,
                    max_iter: int = 100, tol: float = 1e-4) -> float:
    """Fit a single theta (ability) parameter for the Rasch 1PL model.

    difficulties: iterable of item difficulties (expected ~0..1) — these are
    rescaled internally to logit-like offsets. outcomes: iterable of 0/1.
    Returns theta (real number). Regularization 'reg' applies an L2 penalty
    (reg * theta^2).
    """
    import math

    b = [float(x) for x in difficulties]
    y = [1 if int(v) else 0 for v in outcomes]
    n = len(b)
    if n == 0:
        return 0.0

    # Map difficulties in [0,1] to a prior scale centered near 0.
    # A simple transform: b' = (difficulty - 0.5) * 4 -> roughly [-2,2]
    b_scaled = [(val - 0.5) * 4.0 for val in b]

    # initial theta: use logit(mean(y)) + mean(b_scaled)
    mean_y = sum(y) / n
    eps = 1e-3
    if mean_y <= 0:
        theta = -1.0 + sum(b_scaled) / n
    elif mean_y >= 1:
        theta = 1.0 + sum(b_scaled) / n
    else:
        theta = _logit(mean_y) + sum(b_scaled) / n

    # Newton-Raphson
    for _ in range(max_iter):
        ps = [1.0 / (1.0 + math.exp(-(theta - bi))) for bi in b_scaled]
        # gradient: sum(y - p) - 2*reg*theta
        grad = sum(yi - pi for yi, pi in zip(y, ps)) - 2.0 * reg * theta
        # Hessian (second derivative): -sum(p*(1-p)) - 2*reg
        hess = -sum(pi * (1.0 - pi) for pi in ps) - 2.0 * reg
        if hess == 0:
            break
        delta = grad / hess
        theta_new = theta - delta
        if abs(theta_new - theta) < tol:
            theta = theta_new
            break
        theta = theta_new
    return float(theta)
