import { test, expect, Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import path from "node:path";

/**
 * Spec §10's named E2E flow: auth -> attempt -> results/recommendations.
 *
 * Drives the real Next.js build against the real Flask backend on a throwaway
 * SQLite database (see `playwright.config.ts`). Quiz generation itself is
 * seeded rather than driven through the teacher upload UI: the rule-based
 * generator is already covered by the backend suite, and a real upload needs a
 * teacher session plus a file fixture, which would make this flow about
 * uploading rather than about taking a quiz.
 */
const seed = JSON.parse(
  readFileSync(path.join(__dirname, ".seed.json"), "utf8")
) as { quiz_id: number };

// The two seeded questions, and their correct options.
const ANSWERS: Record<string, string> = {
  "What is 2 + 2?": "4",
  "What is the capital of France?": "Paris",
};

function uniqueEmail() {
  return `e2e.student.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.com`;
}

async function registerAndLogin(page: Page, email: string, password: string) {
  await page.goto("/register");
  const registerInputs = page.locator("form input").filter({ hasNot: page.locator("[type=checkbox]") });
  await registerInputs.nth(0).fill("E2E Student");
  await registerInputs.nth(1).fill(email);
  await registerInputs.nth(2).fill(password);
  await page.getByRole("button", { name: /sign up/i }).click();

  await page.waitForURL(/\/login/);
  await page.locator("form input[type=email]").fill(email);
  await page.locator("form input[type=password]").fill(password);
  await page.getByRole("button", { name: /log in|sign in/i }).click();
  await page.waitForURL(/\/dashboard/);
}

test.describe("student quiz flow", () => {
  test("auth -> attempt (answer, feedback, submit) -> results and recommendations", async ({
    page,
  }) => {
    const email = uniqueEmail();
    await registerAndLogin(page, email, "E2eStudentPass123!");

    // --- Attempt -------------------------------------------------------
    // Record the requests the page makes so the E2E run also proves the
    // authenticated-attempt wiring, not just that the UI advances.
    const apiCalls: { url: string; auth: boolean }[] = [];
    page.on("request", (req) => {
      if (req.method() === "POST" && /\/api\//.test(req.url())) {
        apiCalls.push({ url: req.url(), auth: Boolean(req.headers()["authorization"]) });
      }
    });

    await page.goto(`/quiz/${seed.quiz_id}`);

    for (let i = 0; i < Object.keys(ANSWERS).length; i++) {
      const stem = await page.locator("main h1").first().innerText();
      const correct = ANSWERS[stem.trim()];
      expect(correct, `unexpected question stem: ${stem}`).toBeTruthy();

      // The sanitized payload must not have shipped the answer key.
      await expect(page.getByText("Explanation")).toHaveCount(0);

      await page.getByRole("button", { name: correct, exact: true }).click();
      await page.getByRole("button", { name: /^check$/i }).click();

      // Server-side feedback arrived and says this was correct.
      await expect(page.getByText("Correct!")).toBeVisible();
      await page.getByRole("button", { name: /^continue$/i }).click();
    }

    await expect(page.getByText(/Lesson Complete/i)).toBeVisible();
    await expect(page.getByText("2/2")).toBeVisible();

    // The attempt was started authenticated, autosave actually fired, and the
    // submit went through the legacy (gamified) endpoint.
    const attemptStart = apiCalls.find((c) => /\/attempts$/.test(c.url));
    expect(attemptStart, "attempt was never started").toBeTruthy();
    expect(attemptStart!.auth).toBe(true);

    const autosave = apiCalls.filter((c) => /\/responses$/.test(c.url));
    expect(autosave.length).toBe(2);
    expect(autosave.every((c) => c.auth)).toBe(true);

    const feedback = apiCalls.filter((c) => /\/check$/.test(c.url));
    expect(feedback.length).toBe(2);
    expect(feedback.every((c) => c.auth)).toBe(true);

    const submit = apiCalls.find((c) => /\/api\/quizzes\/\d+\/submit$/.test(c.url));
    expect(submit, "quiz was not submitted through the scoring endpoint").toBeTruthy();
    expect(submit!.auth).toBe(true);

    // --- Results / recommendations --------------------------------------
    await page.getByRole("link", { name: /continue/i }).click();
    await page.waitForURL(/\/dashboard/);
    await expect(page.getByText(/Competency|Mastery|Recommend/i).first()).toBeVisible();
  });

  /**
   * Regression for the spec §4.3 attempts route mismatch.
   *
   * The attempts blueprint was mounted only at `/api/v1`, so its real paths
   * were `/api/v1/<id>/result` - missing the `attempts` segment the spec
   * requires. `app/results/[attemptId]/page.tsx` has always fetched
   * `/api/v1/attempts/<id>/result`, so it got a 404 and fell back to its empty
   * state: the student results page could never show feedback in production.
   *
   * This drives the whole flow over the spec-conformant paths against the real
   * server, then loads the real results page in the browser and asserts the
   * feedback actually renders.
   */
  test("results page renders server feedback over the spec /attempts/:id paths", async ({
    page,
    request,
  }) => {
    const api = process.env.PW_API_BASE_URL || "http://127.0.0.1:5101";
    const email = uniqueEmail();
    const password = "E2eResultsPass123!";

    const reg = await request.post(`${api}/api/auth/register`, {
      data: { full_name: "E2E Results", email, password },
    });
    expect(reg.ok()).toBe(true);

    const login = await request.post(`${api}/api/auth/login`, {
      data: { email, password },
    });
    expect(login.ok()).toBe(true);
    const token = (await login.json()).access_token;
    expect(token).toBeTruthy();
    const auth = { Authorization: `Bearer ${token}` };

    // Start attempt (this path was already spec-correct).
    const start = await request.post(
      `${api}/api/v1/quizzes/${seed.quiz_id}/attempts`,
      { headers: auth }
    );
    expect(start.status()).toBe(201);
    const attemptId = (await start.json()).id;

    // Fetch the relational questions so we can answer with real ids/keys.
    const quiz = await request.get(`${api}/api/quizzes/${seed.quiz_id}`);
    const questions = (await quiz.json()).questions as {
      id: number;
      question: string;
      options: string[];
    }[];
    expect(questions.length).toBeGreaterThan(0);

    for (const q of questions) {
      const correctText = ANSWERS[q.question.trim()];
      const key = String.fromCharCode(65 + q.options.indexOf(correctText));
      // Spec path: POST /api/v1/attempts/:id/responses
      const saved = await request.post(
        `${api}/api/v1/attempts/${attemptId}/responses`,
        { headers: auth, data: { question_id: q.id, selected_keys: [key] } }
      );
      expect(saved.status()).toBe(200);
      expect((await saved.json()).is_correct).toBe(true);
    }

    // Spec path: POST /api/v1/attempts/:id/submit
    const submitted = await request.post(
      `${api}/api/v1/attempts/${attemptId}/submit`,
      { headers: auth }
    );
    expect(submitted.status()).toBe(200);
    expect((await submitted.json()).score).toBe(100);

    // Spec path: GET /api/v1/attempts/:id/result - this is the one that 404'd.
    const result = await request.get(
      `${api}/api/v1/attempts/${attemptId}/result`,
      { headers: auth }
    );
    expect(result.status()).toBe(200);
    expect((await result.json()).feedback.length).toBe(questions.length);

    // And the actual page the student sees now renders that feedback.
    await page.goto("/login");
    await page.evaluate((t) => localStorage.setItem("token", t), token);
    await page.goto(`/results/${attemptId}`);
    await expect(page.getByText("Score:")).toBeVisible();
    await expect(page.getByText("100%")).toBeVisible();
    for (const q of questions) {
      await expect(page.getByText(q.question, { exact: false })).toBeVisible();
    }
    await expect(page.getByText("Correct", { exact: true }).first()).toBeVisible();
  });

  test("the quiz payload never contains the answer key for a student", async ({ request }) => {
    const resp = await request.get(
      `${process.env.PW_API_BASE_URL || "http://127.0.0.1:5101"}/api/quizzes/${seed.quiz_id}`
    );
    expect(resp.ok()).toBe(true);
    const body = await resp.text();
    expect(body).not.toContain("correct_answer");
    expect(JSON.parse(body).questions.length).toBeGreaterThan(0);
  });
});
