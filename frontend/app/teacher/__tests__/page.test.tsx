import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TeacherDashboard from "@/app/teacher/page";
import { storeToken } from "@/lib/api";

vi.mock("next/navigation", () => ({
    useRouter: () => ({ push: vi.fn() }),
    usePathname: () => "/teacher",
    useParams: () => ({}),
}));

vi.mock("@/lib/api", async () => {
    const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    return {
        ...actual,
        default: {
            ...actual.default,
            getClasses: vi.fn(),
            inviteStudent: vi.fn(),
            createClass: vi.fn(),
        },
    };
});

import api from "@/lib/api";

const CLASSES = [
    { id: 1, name: "Public Policy", section: "Sem 2", code: "AB12CD", color: "bg-brand-blue" },
    { id: 2, name: "Budgeting", section: "Sem 1", code: "XY99ZZ" },
];

beforeEach(() => {
    localStorage.clear();
    vi.clearAllMocks();
    vi.mocked(api.getClasses).mockResolvedValue([] as never);
});

afterEach(() => vi.restoreAllMocks());

describe("TeacherDashboard", () => {
    it("shows the empty state when the teacher has no classes", async () => {
        render(<TeacherDashboard />);
        expect(await screen.findByText(/You haven't created any classes yet/i)).toBeInTheDocument();
        expect(screen.getByText("Manage 0 active classes.")).toBeInTheDocument();
    });

    it("lists classes with their code, section, and analytics link", async () => {
        vi.mocked(api.getClasses).mockResolvedValue(CLASSES as never);
        render(<TeacherDashboard />);

        expect(await screen.findByText("Public Policy")).toBeInTheDocument();
        expect(screen.getByText("AB12CD")).toBeInTheDocument();
        expect(screen.getByText("Budgeting")).toBeInTheDocument();
        expect(screen.getByText("Manage 2 active classes.")).toBeInTheDocument();

        const analyticsLinks = screen
            .getAllByRole("link")
            .map((a) => a.getAttribute("href"))
            .filter((h) => h?.startsWith("/analytics"));
        expect(analyticsLinks).toEqual(["/analytics?classId=1", "/analytics?classId=2"]);
    });

    it("opens the upload modal from a class card", async () => {
        vi.mocked(api.getClasses).mockResolvedValue(CLASSES as never);
        render(<TeacherDashboard />);
        await userEvent.click((await screen.findAllByRole("button", { name: /material/i }))[0]);
        expect(await screen.findByText("Upload Materials")).toBeInTheDocument();
    });

    it("opens the create-class modal from the header", async () => {
        render(<TeacherDashboard />);
        await userEvent.click(await screen.findByRole("button", { name: /create new class/i }));
        expect(await screen.findByText("Create a New Class")).toBeInTheDocument();
    });

    it("opens the create-class modal from the empty-state CTA", async () => {
        render(<TeacherDashboard />);
        await userEvent.click(await screen.findByRole("button", { name: /create your first class/i }));
        expect(await screen.findByText("Create a New Class")).toBeInTheDocument();
    });

    it("toggles the inline invite form", async () => {
        render(<TeacherDashboard />);
        const toggle = await screen.findByRole("button", { name: /invite student/i });
        expect(screen.queryByText("Full name")).not.toBeInTheDocument();
        await userEvent.click(toggle);
        expect(screen.getByText("Full name")).toBeInTheDocument();
        await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
        expect(screen.queryByText("Full name")).not.toBeInTheDocument();
    });

    it("refuses to invite without a stored token", async () => {
        render(<TeacherDashboard />);
        await userEvent.click(await screen.findByRole("button", { name: /invite student/i }));
        await userEvent.click(screen.getByRole("button", { name: /send invite/i }));
        expect(
            await screen.findByText(/You must be logged in as a teacher to invite students/i)
        ).toBeInTheDocument();
        expect(api.inviteStudent).not.toHaveBeenCalled();
    });

    it("sends an invite and reports the backend message", async () => {
        storeToken("teacher-jwt");
        vi.mocked(api.inviteStudent).mockResolvedValue({ msg: "Invite emailed" } as never);
        render(<TeacherDashboard />);

        await userEvent.click(await screen.findByRole("button", { name: /invite student/i }));
        await userEvent.type(screen.getAllByRole("textbox")[0], "Sam Lee");
        await userEvent.type(screen.getAllByRole("textbox")[1], "sam@x.y");
        await userEvent.click(screen.getByRole("button", { name: /send invite/i }));

        await waitFor(() =>
            expect(api.inviteStudent).toHaveBeenCalledWith("teacher-jwt", {
                email: "sam@x.y",
                full_name: "Sam Lee",
            })
        );
        // Form closes and the result message is shown.
        expect(await screen.findByText("Invite emailed")).toBeInTheDocument();
    });

    it("reports an invite failure", async () => {
        storeToken("teacher-jwt");
        vi.mocked(api.inviteStudent).mockRejectedValue(new Error("Email already registered"));
        render(<TeacherDashboard />);

        await userEvent.click(await screen.findByRole("button", { name: /invite student/i }));
        await userEvent.type(screen.getAllByRole("textbox")[0], "Sam");
        await userEvent.type(screen.getAllByRole("textbox")[1], "sam@x.y");
        await userEvent.click(screen.getByRole("button", { name: /send invite/i }));

        expect(await screen.findByText("Email already registered")).toBeInTheDocument();
    });

    it("recovers from a failing classes request", async () => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        vi.mocked(api.getClasses).mockRejectedValue(new Error("down"));
        render(<TeacherDashboard />);
        expect(await screen.findByText(/You haven't created any classes yet/i)).toBeInTheDocument();
    });
});
