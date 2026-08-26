"""Load-test scenario for spec §10: 500 concurrent quiz takers.

Run against a *disposable* database (never `assesify_dev.db`):

    DATABASE_URL=sqlite:///.../instance/load.db \
      .venv/Scripts/python.exe -m flask --app app.main:app run --port 5000
    .venv/Scripts/locust -f locustfile.py --host http://127.0.0.1:5000 \
      --users 500 --spawn-rate 25 --run-time 5m

`LOAD_QUIZ_ID` must point at a quiz that has relational `Question` rows
(`e2e_seed.py` creates one). Each simulated user registers once, then loops the
real student flow: read the sanitized quiz, start an attempt, autosave one
response per question, ask for per-question feedback, and submit.

Status: authored and validated locally (imports, task wiring and the request
shapes are exercised by `app/tests/test_locustfile.py`); the actual 500-user run
needs a deployment target that does not exist in this environment.
"""
import os
import random
import uuid

from locust import HttpUser, between, task

QUIZ_ID = int(os.environ.get("LOAD_QUIZ_ID", "1"))
PASSWORD = os.environ.get("LOAD_PASSWORD", "LoadTestPass123!")


class QuizTaker(HttpUser):
    """One student taking quizzes back to back."""

    wait_time = between(1, 3)

    def on_start(self):
        """Register and log in a fresh student, so users never collide."""
        self.email = f"load.{uuid.uuid4().hex}@example.com"
        self.token = None

        self.client.post(
            "/api/v1/auth/register",
            json={"email": self.email, "password": PASSWORD, "full_name": "Load Tester"},
            name="POST /auth/register",
        )
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": self.email, "password": PASSWORD},
            name="POST /auth/login",
        )
        if resp.status_code == 200:
            self.token = resp.json().get("access_token")

    @property
    def auth(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(5)
    def take_quiz(self):
        quiz = self.client.get(f"/api/quizzes/{QUIZ_ID}", name="GET /quizzes/:id")
        if quiz.status_code != 200:
            return
        questions = quiz.json().get("questions") or []
        if not questions or not self.token:
            return

        started = self.client.post(
            f"/api/v1/quizzes/{QUIZ_ID}/attempts",
            headers=self.auth,
            name="POST /quizzes/:id/attempts",
        )
        if started.status_code != 201:
            return
        attempt_id = started.json()["id"]

        answers = []
        for question in questions:
            question_id = question.get("id")
            options = question.get("options") or []
            if question_id is None or not options:
                continue
            key = chr(ord("A") + random.randrange(len(options)))

            self.client.post(
                f"/api/v1/{attempt_id}/responses",
                headers=self.auth,
                json={"question_id": question_id, "selected_keys": [key]},
                name="POST /:attempt/responses",
            )
            self.client.post(
                f"/api/quizzes/{QUIZ_ID}/questions/{question_id}/check",
                headers=self.auth,
                json={"attempt_id": attempt_id},
                name="POST /quizzes/:id/questions/:qid/check",
            )
            answers.append({
                "question_id": question_id,
                "selected_keys": [key],
                "question": question.get("question"),
                "answer": options[ord(key) - ord("A")],
            })

        self.client.post(
            f"/api/quizzes/{QUIZ_ID}/submit",
            headers=self.auth,
            json={"answers": answers},
            name="POST /quizzes/:id/submit",
        )

    @task(1)
    def read_recommendations(self):
        """The analytics read path students hit from the dashboard."""
        if not self.token:
            return
        profile = self.client.get("/api/v1/auth/profile", headers=self.auth,
                                  name="GET /auth/profile")
        if profile.status_code != 200:
            return
        student_id = profile.json().get("id")
        if student_id is None:
            return
        self.client.get(f"/api/v1/students/{student_id}/mastery", headers=self.auth,
                        name="GET /students/:id/mastery")
        self.client.get(f"/api/v1/students/{student_id}/recommendations", headers=self.auth,
                        name="GET /students/:id/recommendations")
