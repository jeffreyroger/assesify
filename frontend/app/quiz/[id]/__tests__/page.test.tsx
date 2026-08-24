import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

vi.mock("next/navigation", () => ({
    useParams: () => ({ id: "1" }),
}));

import QuizPage from "../page";

const mockQuestion = {
    id: 101,
    question: "What is the capital of France?",
    answer: "Paris has been the capital of France since the 10th century.",
    options: ["Paris", "Berlin", "Madrid", "Rome"],
    correct_answer: "Paris",
    hint: "Think Eiffel Tower.",
};

function setupFetchMock() {
    const calls: { url: string; method: string; body?: unknown }[] = [];

    global.fetch = vi.fn((url: string, opts?: RequestInit) => {
        const method = opts?.method || "GET";
        calls.push({ url, method, body: opts?.body ? JSON.parse(opts.body as string) : undefined });

        if (url.includes("/api/quizzes/1") && method === "GET") {
            return Promise.resolve({
                ok: true,
                json: async () => ({ questions: [mockQuestion] }),
            } as Response);
        }
        if (url.includes("/attempts") && method === "POST") {
            return Promise.resolve({
                ok: true,
                json: async () => ({ id: 42 }),
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
        setupFetchMock();
    });

    afterEach(() => {
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

        // Autosave call to /api/v1/<attemptId>/responses with the selected key.
        await waitFor(() => {
            expect(calls.some((c) => c.url.includes("/responses") && c.method === "POST")).toBe(
                true
            );
        });
        const responseCall = calls.find((c) => c.url.includes("/responses"));
        expect(responseCall?.body).toMatchObject({ question_id: 101, selected_keys: ["A"] });

        // Only one question in this quiz, so Continue finalizes the attempt.
        await user.click(screen.getByRole("button", { name: /continue/i }));

        await waitFor(() => {
            expect(
                calls.some((c) => c.url.includes("/42/submit") && c.method === "POST")
            ).toBe(true);
        });
        expect(await screen.findByText(/Lesson Complete/i)).toBeInTheDocument();
    });
});
