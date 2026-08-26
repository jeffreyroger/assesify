import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
    useParams: () => ({ id: "1" }),
}));

import QuizPage from "../page";

// The *real* sanitized student payload from GET /api/quizzes/:id, i.e. exactly
// what `quiz_generation.legacy_shape_from_questions()` emits for a non-owner:
// no `correct_answer` and no `answer` (explanation). Those reach the client only
// via POST /api/quizzes/:id/questions/:questionId/check, once a selection is
// committed. Do not add answer fields back to this fixture - it would let a
// test pass against a payload production never sends.
const mockQuestion = {
    id: 101,
    question: "What is the capital of France?",
    options: ["Paris", "Berlin", "Madrid", "Rome"],
    hint: "Think Eiffel Tower.",
};

// The per-question feedback the check endpoint returns for this fixture.
const CHECK_FEEDBACK = {
    question_id: 101,
    is_correct: true,
    correct_answer: "Paris",
    correct_keys: ["A"],
    explanation: "Paris has been the capital of France since the 10th century.",
};

function setupFetchMock(
    opts_: { attemptOk?: boolean; question?: unknown; checkOk?: boolean; feedback?: unknown } = {}
) {
    const {
        attemptOk = true,
        question = mockQuestion,
        checkOk = true,
        feedback = CHECK_FEEDBACK,
    } = opts_;
    const calls: {
        url: string;
        method: string;
        body?: unknown;
        headers?: Record<string, string>;
    }[] = [];

    global.fetch = vi.fn((url: string, opts?: RequestInit) => {
        const method = opts?.method || "GET";
        calls.push({
            url,
            method,
            body: opts?.body ? JSON.parse(opts.body as string) : undefined,
            headers: (opts?.headers as Record<string, string>) ?? {},
        });

        if (url.includes("/check") && method === "POST") {
            return Promise.resolve({
                ok: checkOk,
                json: async () => (checkOk ? feedback : {}),
            } as Response);
        }
        if (url.includes("/api/quizzes/1") && method === "GET") {
            // Full envelope, as Quiz.to_dict() actually returns it.
            return Promise.resolve({
                ok: true,
                json: async () => ({
                    id: 1,
                    lesson_id: 7,
                    questions: [question],
                    created_at: "2026-01-01T00:00:00",
                }),
            } as Response);
        }
        if (url.includes("/attempts") && method === "POST") {
            return Promise.resolve({
                ok: attemptOk,
                json: async () => (attemptOk ? { id: 42 } : {}),
            } as Response);
        }
        if (url.includes("/responses") && method === "POST") {
            return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
        }
        if (url.includes("/submit") && method === "POST") {
            return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
        }
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    }) as unknown as typeof fetch;

    return calls;
}

describe("Quiz-taking page (app/quiz/[id]/page.tsx)", () => {
    beforeEach(() => {
        // Both /check and the legacy /submit are @jwt_required on the server, so
        // the page has to be exercised with a stored token - otherwise a test can
        // pass against a request production would 401 on.
        localStorage.clear();
        localStorage.setItem("token", "test-token");
        setupFetchMock();
    });

    afterEach(() => {
        localStorage.clear();
        vi.restoreAllMocks();
    });

    it("renders the question and its answer options once loaded", async () => {
        render(<QuizPage />);

        expect(await screen.findByText("What is the capital of France?")).toBeInTheDocument();
        expect(screen.getByText("Paris")).toBeInTheDocument();
        expect(screen.getByText("Berlin")).toBeInTheDocument();
        // Check button starts disabled until an option is selected.
        expect(screen.getByRole("button", { name: /check/i })).toBeDisabled();
    });

    it("selecting an option updates state and enables the Check button", async () => {
        const user = userEvent.setup();
        render(<QuizPage />);

        const parisOption = await screen.findByText("Paris");
        await user.click(parisOption);

        expect(screen.getByRole("button", { name: /check/i })).toBeEnabled();
    });

    it("checking an answer autosaves the response and submits on the final Continue click", async () => {
        const user = userEvent.setup();
        const calls = setupFetchMock();
        render(<QuizPage />);

        const parisOption = await screen.findByText("Paris");
        await user.click(parisOption);
        await user.click(screen.getByRole("button", { name: /check/i }));

        // Autosave call to /api/v1/attempts/<attemptId>/responses with the selected key.
        await waitFor(() => {
            expect(calls.some((c) => c.url.includes("/responses") && c.method === "POST")).toBe(
                true
            );
        });
        const responseCall = calls.find((c) => c.url.includes("/responses"));
        // A real relational question_id, not a placeholder, and the option key.
        expect(responseCall?.body).toMatchObject({ question_id: 101, selected_keys: ["A"] });
        expect(responseCall?.url).toContain("/api/v1/attempts/42/responses");
        // POST /api/v1/attempts/<attempt>/responses is @jwt_required; without this
        // header the autosave 401s and no `responses` row is ever written.
        expect(responseCall?.headers?.Authorization).toBe("Bearer test-token");

        // The attempt itself must be started authenticated - that is what makes
        // attemptId non-null and the autosave possible at all.
        const attemptCall = calls.find((c) => c.url.includes("/attempts"));
        expect(attemptCall?.headers?.Authorization).toBe("Bearer test-token");

        // Only one question in this quiz, so Continue finalizes the attempt.
        await user.click(screen.getByRole("button", { name: /continue/i }));

        // Even with an open attempt the page submits through the legacy
        // endpoint - it is the score of record and the only path that awards
        // gamification. /api/v1/<attempt>/submit must never be called.
        await waitFor(() => {
            expect(
                calls.some((c) => c.url.includes("/api/quizzes/1/submit") && c.method === "POST")
            ).toBe(true);
        });
        expect(calls.some((c) => c.url.includes("/42/submit"))).toBe(false);
        expect(await screen.findByText(/Lesson Complete/i)).toBeInTheDocument();
    });

    it("submits the real question_id and the student's actual selection when no attempt is active", async () => {
        const user = userEvent.setup();
        // No attempt can be started (e.g. unauthenticated), so the page falls
        // back to the legacy POST /api/quizzes/:id/submit endpoint.
        const calls = setupFetchMock({
            attemptOk: false,
            feedback: { ...CHECK_FEEDBACK, is_correct: false },
        });
        render(<QuizPage />);

        const berlinOption = await screen.findByText("Berlin");
        await user.click(berlinOption);
        await user.click(screen.getByRole("button", { name: /check/i }));
        await user.click(screen.getByRole("button", { name: /continue/i }));

        await waitFor(() => {
            expect(
                calls.some((c) => c.url.includes("/api/quizzes/1/submit") && c.method === "POST")
            ).toBe(true);
        });

        const submitCall = calls.find((c) => c.url.includes("/api/quizzes/1/submit"));
        // POST /api/quizzes/:id/submit is @jwt_required too.
        expect(submitCall?.headers?.Authorization).toBe("Bearer test-token");
        const body = submitCall?.body as { answers: Record<string, unknown>[] };
        expect(body.answers).toHaveLength(1);
        // Real relational question id + the student's actual selection ("Berlin"
        // is option B), not the old "Submitted via API" placeholder.
        expect(body.answers[0]).toMatchObject({
            question_id: 101,
            selected_keys: ["B"],
            answer: "Berlin",
            question: "What is the capital of France?",
        });
    });

    it("never receives the correct answer in the quiz payload, and asks /check for it on Check", async () => {
        const user = userEvent.setup();
        const calls = setupFetchMock();
        render(<QuizPage />);

        // Before checking, nothing on screen reveals the answer.
        await screen.findByText("Paris");
        expect(screen.queryByText(/Explanation/i)).not.toBeInTheDocument();
        // The only request so far is the sanitized GET + the attempt start.
        expect(calls.some((c) => c.url.includes("/check"))).toBe(false);

        await user.click(screen.getByText("Paris"));
        await user.click(screen.getByRole("button", { name: /check/i }));

        await waitFor(() => {
            expect(calls.some((c) => c.url.includes("/check"))).toBe(true);
        });
        const checkCall = calls.find((c) => c.url.includes("/check"))!;
        // Per-question path, carrying only the selection just committed.
        expect(checkCall.url).toContain("/api/quizzes/1/questions/101/check");
        expect(checkCall.method).toBe("POST");
        // Feedback is bound to the student's attempt; the server reveals only a
        // question already answered in it.
        expect(checkCall.body).toEqual({ attempt_id: 42 });
        // The endpoint is @jwt_required; without this header it would 401.
        expect(checkCall.headers?.Authorization).toBe("Bearer test-token");
    });

    it("renders review feedback from the server response, not from the quiz payload", async () => {
        const user = userEvent.setup();
        setupFetchMock({
            feedback: {
                question_id: 101,
                is_correct: false,
                correct_answer: "Paris",
                correct_keys: ["A"],
                explanation: "Paris has been the capital of France since the 10th century.",
            },
        });
        render(<QuizPage />);

        await user.click(await screen.findByText("Berlin"));
        await user.click(screen.getByRole("button", { name: /check/i }));

        // Explanation text only ever came from the server.
        expect(
            await screen.findByText(/Paris has been the capital of France/i)
        ).toBeInTheDocument();
        expect(await screen.findByText(/Incorrect/i)).toBeInTheDocument();
    });

    it("falls back gracefully when the check request fails", async () => {
        const user = userEvent.setup();
        setupFetchMock({ checkOk: false });
        render(<QuizPage />);

        await user.click(await screen.findByText("Paris"));
        await user.click(screen.getByRole("button", { name: /check/i }));

        // Still advances to review mode with a working Continue button rather
        // than stalling on the Check button.
        expect(await screen.findByRole("button", { name: /continue/i })).toBeEnabled();
    });

    it("omits question_id for legacy quizzes whose questions carry no id", async () => {
        const user = userEvent.setup();
        // A pre-relational blob quiz: no id, and (because the blob path is
        // sanitized too) no correct_answer either, so no feedback is available.
        const { id: _omitted, ...legacyQuestion } = mockQuestion;
        const calls = setupFetchMock({ attemptOk: false, question: legacyQuestion });
        render(<QuizPage />);

        const parisOption = await screen.findByText("Paris");
        await user.click(parisOption);
        await user.click(screen.getByRole("button", { name: /check/i }));
        await user.click(screen.getByRole("button", { name: /continue/i }));

        await waitFor(() => {
            expect(
                calls.some((c) => c.url.includes("/api/quizzes/1/submit") && c.method === "POST")
            ).toBe(true);
        });

        const submitCall = calls.find((c) => c.url.includes("/api/quizzes/1/submit"));
        const body = submitCall?.body as { answers: Record<string, unknown>[] };
        // Legacy payload preserved verbatim for clients/quizzes without ids.
        expect(body.answers[0]).not.toHaveProperty("question_id");
        expect(body.answers[0]).toMatchObject({
            question: "What is the capital of France?",
            answer: "Paris",
        });
        // No id => no /check round-trip is even attempted.
        expect(calls.some((c) => c.url.includes("/check"))).toBe(false);
    });
});
