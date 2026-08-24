import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DashboardPage from "@/app/dashboard/page";
import { storeUser, storeToken } from "@/lib/api";

vi.mock("next/navigation", () => ({
    useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
    usePathname: () => "/dashboard",
    useParams: () => ({}),
}));

vi.mock("@/lib/api", async () => {
    const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    return {
        ...actual,
        default: {
            ...actual.default,
            getClasses: vi.fn(),
            getLessons: vi.fn(),
            getRecentQuizzes: vi.fn(),
            getWeeklyPerformance: vi.fn(),
            generateWeeklyTest: vi.fn(),
        },
    };
});

import api from "@/lib/api";

const STUDENT = { id: 1, full_name: "Asha Rao", is_teacher: false, streak: 4, diamonds: 12, health: 3 };
const TEACHER = { id: 2, full_name: "Ravi Kumar", is_teacher: true };

function primeApi(overrides: Partial<Record<string, unknown>> = {}) {
    vi.mocked(api.getClasses).mockResolvedValue((overrides.classes as never) ?? []);
    vi.mocked(api.getLessons).mockResolvedValue((overrides.lessons as never) ?? []);
    vi.mocked(api.getRecentQuizzes).mockResolvedValue((overrides.recentQuizzes as never) ?? []);
    vi.mocked(api.getWeeklyPerformance).mockResolvedValue((overrides.weekly as never) ?? { topics: [] });
}

beforeEach(() => {
    localStorage.clear();
    storeToken("jwt");
    vi.clearAllMocks();
    // MasteryRecommendations fetches directly with fetch().
    global.fetch = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ mastery: [], recommendations: [] }),
    } as Response);
});

afterEach(() => vi.restoreAllMocks());

describe("DashboardPage — student view", () => {
    it("greets the user by first name and shows gamification stats", async () => {
        storeUser(STUDENT);
        primeApi();
        render(<DashboardPage />);

        expect(await screen.findByText("Asha")).toBeInTheDocument();
        expect(screen.getByText("🔥 4")).toBeInTheDocument();
        expect(screen.getByText("💎 12")).toBeInTheDocument();
        expect(screen.getByText("❤️ 3")).toBeInTheDocument();
        expect(screen.getByText(/Ready for today's challenges/i)).toBeInTheDocument();
    });

    it("offers Join Class rather than the teacher actions", async () => {
        storeUser(STUDENT);
        primeApi();
        render(<DashboardPage />);
        expect(await screen.findByRole("button", { name: /join class/i })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /upload topic/i })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /invite student/i })).not.toBeInTheDocument();
    });

    it("shows the weekly-test empty state when there is no activity", async () => {
        storeUser(STUDENT);
        primeApi({ weekly: { topics: [] } });
        render(<DashboardPage />);
        expect(await screen.findByText(/No quiz activity this week yet/i)).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /generate weekly test/i })).not.toBeInTheDocument();
    });

    it("renders weekly topic accuracy and generates a weekly test", async () => {
        storeUser(STUDENT);
        primeApi({ weekly: { topics: [{ topic: "budgeting", accuracy: 45 }, { topic: "policy", accuracy: 85 }] } });
        vi.mocked(api.generateWeeklyTest).mockResolvedValue({ id: 77 } as never);
        render(<DashboardPage />);

        expect(await screen.findByText("budgeting")).toBeInTheDocument();
        expect(screen.getByText("45%")).toBeInTheDocument();
        expect(screen.getByText("85%")).toBeInTheDocument();

        await userEvent.click(screen.getByRole("button", { name: /generate weekly test/i }));
        await waitFor(() => expect(api.generateWeeklyTest).toHaveBeenCalledTimes(1));
        const [userId, numQuestions] = vi.mocked(api.generateWeeklyTest).mock.calls[0];
        expect(userId).toBe(1);
        expect(numQuestions).toBe(10);
    });

    it("alerts when weekly-test generation fails", async () => {
        storeUser(STUDENT);
        primeApi({ weekly: { topics: [{ topic: "budgeting", accuracy: 45 }] } });
        vi.mocked(api.generateWeeklyTest).mockRejectedValue(new Error("Gemini unavailable"));
        const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
        vi.spyOn(console, "error").mockImplementation(() => {});
        render(<DashboardPage />);

        await userEvent.click(await screen.findByRole("button", { name: /generate weekly test/i }));
        await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Gemini unavailable"));
    });

    it("shows the student empty state for classes", async () => {
        storeUser(STUDENT);
        primeApi({ classes: [] });
        render(<DashboardPage />);
        expect(await screen.findByText(/You haven't joined any classes yet/i)).toBeInTheDocument();
    });

    it("opens the join-class modal from the empty state", async () => {
        storeUser(STUDENT);
        primeApi({ classes: [] });
        render(<DashboardPage />);
        const ctas = await screen.findAllByRole("button", { name: /join class/i });
        await userEvent.click(ctas[ctas.length - 1]);
        // The join modal is identified by its class-code field.
        expect(await screen.findByPlaceholderText(/XY12Z3/i)).toBeInTheDocument();
    });

    it("lists joined classes with a link into each one", async () => {
        storeUser(STUDENT);
        primeApi({ classes: [{ id: 5, name: "Civics", section: "Sem 2", teacher: "Ravi Kumar" }] });
        render(<DashboardPage />);
        expect(await screen.findByText("Civics")).toBeInTheDocument();
        expect(screen.getByText("Sem 2")).toBeInTheDocument();
        expect(screen.getByText("Ravi Kumar")).toBeInTheDocument();
        const link = screen.getByText(/Enter Class/i).closest("a");
        expect(link).toHaveAttribute("href", "/class/5");
    });

    it("prefers real recent quizzes over the placeholder list", async () => {
        storeUser(STUDENT);
        primeApi({
            recentQuizzes: [{ id: 9, title: "Budget Cycles Quiz", topic: "budgeting", questions_count: 8 }],
        });
        render(<DashboardPage />);
        expect(await screen.findByText("Budget Cycles Quiz")).toBeInTheDocument();
        expect(screen.getByText("budgeting")).toBeInTheDocument();
        expect(screen.getByText(/16 min/)).toBeInTheDocument();
        expect(screen.queryByText("Photosynthesis Quiz")).not.toBeInTheDocument();
    });

    it("falls back to placeholder quizzes when none are returned", async () => {
        storeUser(STUDENT);
        primeApi({ recentQuizzes: [] });
        render(<DashboardPage />);
        expect(await screen.findByText("Photosynthesis Quiz")).toBeInTheDocument();
        expect(screen.getByText("Urgent")).toBeInTheDocument();
    });

    it("survives failing API calls without crashing", async () => {
        storeUser(STUDENT);
        vi.spyOn(console, "error").mockImplementation(() => {});
        vi.mocked(api.getClasses).mockRejectedValue(new Error("down"));
        vi.mocked(api.getLessons).mockRejectedValue(new Error("down"));
        vi.mocked(api.getRecentQuizzes).mockRejectedValue(new Error("down"));
        vi.mocked(api.getWeeklyPerformance).mockRejectedValue(new Error("down"));
        render(<DashboardPage />);
        expect(await screen.findByText(/You haven't joined any classes yet/i)).toBeInTheDocument();
    });
});

describe("DashboardPage — teacher view", () => {
    beforeEach(() => storeUser(TEACHER));

    it("shows teacher actions and copy, not the student stats", async () => {
        primeApi();
        render(<DashboardPage />);
        expect(await screen.findByRole("button", { name: /upload topic/i })).toBeInTheDocument();
        expect(screen.getAllByRole("button", { name: /create class/i }).length).toBeGreaterThan(0);
        expect(screen.getByRole("button", { name: /invite student/i })).toBeInTheDocument();
        expect(screen.getByText(/Manage your classes and upload new study materials/i)).toBeInTheDocument();
        expect(screen.queryByText(/Weekly Test/i)).not.toBeInTheDocument();
        expect(screen.queryByText("Streak")).not.toBeInTheDocument();
    });

    it("does not request weekly performance for a teacher", async () => {
        primeApi();
        render(<DashboardPage />);
        await screen.findByRole("button", { name: /upload topic/i });
        expect(api.getWeeklyPerformance).not.toHaveBeenCalled();
    });

    it("opens the create-class modal", async () => {
        primeApi();
        render(<DashboardPage />);
        const ctas = await screen.findAllByRole("button", { name: /create class/i });
        await userEvent.click(ctas[0]);
        expect(await screen.findByText("Create a New Class")).toBeInTheDocument();
    });

    it("opens the invite-student modal", async () => {
        primeApi();
        render(<DashboardPage />);
        await userEvent.click(await screen.findByRole("button", { name: /invite student/i }));
        // The invite modal is identified by its student-name field.
        expect(await screen.findByPlaceholderText("Student Name")).toBeInTheDocument();
    });

    it("shows the teacher-specific classes empty state", async () => {
        primeApi({ classes: [] });
        render(<DashboardPage />);
        expect(await screen.findByText(/You haven't created any classes yet/i)).toBeInTheDocument();
    });
});
