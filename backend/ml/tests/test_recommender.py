import os
import sys

sys.path.insert(0, r"c:/Users/Home/Desktop/backend/assesify/backend")

from ml.pipeline import load_data, preprocess
from ml.recommender import advanced_aggregate, recommend_actions, build_personalized_prompt


def test_recommender_flow():
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "sample_attempts.csv")
    df = load_data(csv_path)
    assert not df.empty

    dfp = preprocess(df)
    agg = advanced_aggregate(dfp)
    assert "accuracy_mean" in agg.columns
    assert "speed_score" in agg.columns

    actions = recommend_actions(agg, "s1", top_n=2)
    assert isinstance(actions, list)
    if actions:
        a = actions[0]
        prompt = build_personalized_prompt(a, n_questions=3)
        assert isinstance(prompt, str)
        assert "Topic:" in prompt
