"""Personalized recommendation engine for quiz generation and adaptive learning.

This module separates preprocessing, feature engineering, profiling, inference, and recommendation logic.
It is deliberately interpretable using simple rule-based and lightweight ML components.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional
# pandas is optional for runtime; import lazily to avoid breaking test imports when pandas is unavailable
try:
    import pandas as pd
except Exception:
    pd = None
try:
    import numpy as np
except Exception:
    np = None


@dataclass
class TopicAction:
    student_id: str
    topic: str
    subtopic: Optional[str]
    action: str  # one of: revise, practice, assess, advance
    recommended_difficulty: str  # easy/medium/hard
    reason: str
    learning_objective: str
    weaknesses: List[str]


def advanced_aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate features per (student, topic, subtopic).

    Adds:
    - accuracy_mean, accuracy_std
    - avg_time_mean
    - attempts_count
    - improvement_slope
    - success_easy/medium/hard counts and rates
    - speed_score (lower time -> higher score [0-1])
    - consistency_score (based on accuracy std)
    """
    df = df.copy()
    df = df.sort_values("attempt_date")

    groups = []
    # Ensure subtopic exists (older datasets may not include it)
    if "subtopic" not in df.columns:
        df["subtopic"] = None

    for (sid, topic, subtopic), g in df.groupby(["student_id", "topic", "subtopic"]):
        accuracy_mean = g["accuracy"].mean()
        accuracy_std = g["accuracy"].std(ddof=0) if len(g) > 1 else 0.0
        avg_time_mean = g["avg_time_per_question"].mean()
        attempts_count = len(g)

        # improvement slope (accuracy over time)
        if len(g) >= 2:
            x = (g["attempt_date"]).apply(lambda d: d.timestamp()).values
            y = g["accuracy"].values
            cov = np.cov(x, y, bias=True)[0, 1]
            varx = np.var(x) if np.var(x) != 0 else 1.0
            slope = cov / varx
        else:
            slope = 0.0

        # difficulty success metrics
        def success_stat(level: str):
            sub = g[g["difficulty"] == level]
            return {
                "count": len(sub),
                "mean": float(sub["accuracy"].mean()) if len(sub) > 0 else np.nan,
            }

        easy = success_stat("easy")
        medium = success_stat("medium")
        hard = success_stat("hard")

        groups.append({
            "student_id": sid,
            "topic": topic,
            "subtopic": subtopic,
            "accuracy_mean": accuracy_mean,
            "accuracy_std": accuracy_std,
            "avg_time_mean": avg_time_mean,
            "attempts_count": attempts_count,
            "improvement_slope": slope,
            "easy_count": easy["count"],
            "easy_mean": easy["mean"] if not np.isnan(easy["mean"]) else 0.0,
            "medium_count": medium["count"],
            "medium_mean": medium["mean"] if not np.isnan(medium["mean"]) else 0.0,
            "hard_count": hard["count"],
            "hard_mean": hard["mean"] if not np.isnan(hard["mean"]) else 0.0,
        })

    out = pd.DataFrame(groups)

    # Speed score: invert avg_time_mean, scaled 0-1 using robust min/max
    if not out["avg_time_mean"].isnull().all():
        q1 = out["avg_time_mean"].quantile(0.05)
        q99 = out["avg_time_mean"].quantile(0.95)
        denom = max(q99 - q1, 1e-6)
        out["speed_score"] = 1.0 - ((out["avg_time_mean"] - q1).clip(lower=0) / denom)
        out["speed_score"] = out["speed_score"].clip(0.0, 1.0)
    else:
        out["speed_score"] = 0.5

    # Consistency score: 1 - normalized std (higher is more consistent)
    std_q1 = out["accuracy_std"].quantile(0.05)
    std_q99 = out["accuracy_std"].quantile(0.95)
    denom2 = max(std_q99 - std_q1, 1e-6)
    out["consistency_score"] = 1.0 - ((out["accuracy_std"] - std_q1).clip(lower=0) / denom2)
    out["consistency_score"] = out["consistency_score"].clip(0.0, 1.0)

    # Identify weakness concepts: low difficulty mean or low overall accuracy
    out["weakness_score"] = (1.0 - out["accuracy_mean"]) * 0.6 + (1.0 - out["medium_mean"]) * 0.2 + (1.0 - out["hard_mean"]) * 0.2
    out["weakness_score"] = out["weakness_score"].clip(0.0, 1.0)

    return out


def profile_student_topic(row: pd.Series) -> Dict[str, Any]:
    """Simple interpretable rules to categorize students per topic.

    Returns a dict with:
    - mastery: Weak/Average/Strong
    - level: Beginner/Intermediate/Advanced (mirrors mastery but can include more signals)
    - behavior: fast_learner / slow_but_accurate / inconsistent / steady
    """
    acc = row.get("accuracy_mean", 0.0)
    slope = row.get("improvement_slope", 0.0)
    speed = row.get("speed_score", 0.5)
    consistency = row.get("consistency_score", 0.5)

    if acc < 0.5:
        mastery = "Weak"
        level = "Beginner"
    elif acc < 0.8:
        mastery = "Average"
        level = "Intermediate"
    else:
        mastery = "Strong"
        level = "Advanced"

    # Behavior patterns
    if slope > 0.01 and acc >= 0.6:
        behavior = "fast_learner"
    elif speed < 0.4 and acc >= 0.7:
        behavior = "slow_but_accurate"
    elif consistency < 0.4:
        behavior = "inconsistent"
    else:
        behavior = "steady"

    return {"mastery": mastery, "level": level, "behavior": behavior}


def recommend_actions(agg_df: pd.DataFrame, student_id: str, top_n: int = 3) -> List[TopicAction]:
    """Produce a ranked list of TopicAction objects for the student.

    Rules (interpretable):
    - Weak & non-improving -> action=revise, difficulty=easy
    - Weak but improving -> practice, difficulty=easy
    - Average & improving -> practice, difficulty=medium
    - Average & flat/declining -> revise/practice, difficulty=medium
    - Strong & improving -> advance, difficulty=hard
    - Strong but inconsistent -> assess, difficulty=medium

    The learning_objective is templated; weaknesses are derived from low per-difficulty means.
    """
    s = agg_df[agg_df["student_id"] == student_id]
    actions: List[TopicAction] = []
    if s.empty:
        return actions

    # Rank by weakness_score descending
    s = s.sort_values("weakness_score", ascending=False).head(top_n)

    for _, row in s.iterrows():
        p = profile_student_topic(row)
        acc = row["accuracy_mean"]
        slope = row["improvement_slope"]
        weak_subs = []
        if row["easy_mean"] < 0.6:
            weak_subs.append("easy_concepts")
        if row["medium_mean"] < 0.6:
            weak_subs.append("medium_concepts")
        if row["hard_mean"] < 0.5:
            weak_subs.append("hard_concepts")

        # Rule set
        if p["mastery"] == "Weak":
            if slope <= 0.0:
                action = "revise"
                diff = "easy"
            else:
                action = "practice"
                diff = "easy"
        elif p["mastery"] == "Average":
            if slope > 0.0:
                action = "practice"
                diff = "medium"
            else:
                action = "revise"
                diff = "medium"
        else:  # Strong
            if p["behavior"] == "inconsistent":
                action = "assess"
                diff = "medium"
            else:
                action = "advance"
                diff = "hard"

        lo = f"Fill knowledge gaps in {row['topic']}:{row['subtopic']} - focus on {' & '.join(weak_subs) if weak_subs else 'key concepts'}"

        actions.append(
            TopicAction(
                student_id=row["student_id"],
                topic=row["topic"],
                subtopic=row["subtopic"],
                action=action,
                recommended_difficulty=diff,
                reason=f"mastery={p['mastery']} acc={acc:.2f} slope={slope:.4f} behavior={p['behavior']}",
                learning_objective=lo,
                weaknesses=weak_subs,
            )
        )

    return actions


def build_personalized_prompt(action: TopicAction, n_questions: int = 5, tone: str = "encouraging") -> str:
    """Build a Gemini prompt tailored to the student's action and weaknesses.

    The prompt requests JSON with items including question, choices (4), correct answer, explanation, difficulty, and learning_objective.
    It also includes a short note with the student's profile to increase personalization.
    """
    prompt = (
        "You are an expert educational content writer. Return ONLY valid JSON with a top-level object containing a 'quiz' array. "
        "Each quiz item must be an object: {\n  'question': str,\n  'choices': [str],\n  'answer': str,\n  'explanation': str,\n  'difficulty': str,\n  'learning_objective': str\n}\n"
        f"Topic: {action.topic}\n"
        f"Subtopic: {action.subtopic}\n"
        f"Difficulty: {action.recommended_difficulty}\n"
        f"Learning objective: {action.learning_objective}\n"
        f"Student behavior note: {action.reason}. Weaknesses: {', '.join(action.weaknesses) if action.weaknesses else 'none'}\n"
        f"Tone: {tone}\n"
        f"Number of questions: {n_questions}\n\n"
        "Requirements:\n"
        "- Align each question with the learning objective and weaknesses.\n"
        "- Provide 4 plausible distractors for each MCQ.\n"
        "- Ensure questions vary in scaffolded difficulty and align to the requested difficulty level.\n"
        "- For each question include a one-sentence explanation of the correct answer.\n"
        "Return only valid JSON."
    )
    return prompt


# Utility to create a simple uniqueness seed so no two students get the same quiz content
def personalization_seed(student_id: str, topic: str, subtopic: Optional[str]) -> str:
    return f"seed:{student_id}:{topic}:{subtopic}"


def generate_quiz_from_action(gemini_client: Any, action: TopicAction, n_questions: int = 5, tone: str = "encouraging") -> dict:
    """Use a Gemini client to generate a quiz JSON from a TopicAction.

    The gemini_client is expected to have a `generate_json(prompt)` method that returns parsed JSON.
    """
    prompt = build_personalized_prompt(action, n_questions=n_questions, tone=tone)
    # Optionally attach a small personalization seed to encourage unique outputs
    seed = personalization_seed(action.student_id, action.topic, action.subtopic)
    prompt = f"<!-- {seed} -->\n" + prompt

    # Call the client
    resp = gemini_client.generate_json(prompt)
    return resp
