import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Button } from "@/components/Button";
import { Card } from "@/components/Card";
import { ProgressBar } from "@/components/ProgressBar";
import { MobileNav } from "@/components/MobileNav";
import { Sidebar } from "@/components/Sidebar";
import { TopicsToReview } from "@/components/TopicsToReview";
import { storeUser } from "@/lib/api";

const mockPathname = vi.fn(() => "/dashboard");
vi.mock("next/navigation", () => ({
    usePathname: () => mockPathname(),
}));

vi.mock("@/lib/api", async () => {
    const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    return {
        ...actual,
        default: { ...actual.default, getLessons: vi.fn() },
    };
});

import api from "@/lib/api";

describe("Button", () => {
    it("renders its children and fires onClick", async () => {
        const onClick = vi.fn();
        render(<Button onClick={onClick}>Continue</Button>);
        await userEvent.click(screen.getByRole("button", { name: "Continue" }));
        expect(onClick).toHaveBeenCalledTimes(1);
    });

    it("applies variant and size classes", () => {
        const { rerender } = render(<Button variant="danger" size="lg">Delete</Button>);
        const button = screen.getByRole("button");
        expect(button.className).toContain("bg-brand-red");
        expect(button.className).toContain("h-14");

        rerender(<Button variant="ghost" size="sm">Quiet</Button>);
        expect(screen.getByRole("button").className).toContain("bg-transparent");
        // ghost is the one variant without the raised bottom border
        expect(screen.getByRole("button").className).not.toContain("border-b-4");
    });

    it("does not fire onClick while disabled", async () => {
        const onClick = vi.fn();
        render(<Button disabled onClick={onClick}>Nope</Button>);
        await userEvent.click(screen.getByRole("button"));
        expect(onClick).not.toHaveBeenCalled();
    });
});

describe("Card", () => {
    it("renders children with default padding", () => {
        render(<Card data-testid="card">Inside</Card>);
        const card = screen.getByTestId("card");
        expect(card).toHaveTextContent("Inside");
        expect(card.className).toContain("p-6");
    });

    it("drops padding when noPadding is set and merges custom classes", () => {
        render(<Card data-testid="card" noPadding className="custom-class">X</Card>);
        const card = screen.getByTestId("card");
        expect(card.className).not.toContain("p-6");
        expect(card.className).toContain("custom-class");
    });
});

describe("ProgressBar", () => {
    it("renders the fill at the given percentage", () => {
        const { container } = render(<ProgressBar value={40} />);
        const fill = container.firstElementChild!.firstElementChild as HTMLElement;
        expect(fill.style.width).toBe("40%");
    });

    it("clamps values to the 5-100 range", () => {
        const { container, rerender } = render(<ProgressBar value={0} />);
        expect((container.firstElementChild!.firstElementChild as HTMLElement).style.width).toBe("5%");
        rerender(<ProgressBar value={250} />);
        expect((container.firstElementChild!.firstElementChild as HTMLElement).style.width).toBe("100%");
    });

    it("applies the requested colour", () => {
        const { container } = render(<ProgressBar value={50} color="blue" />);
        const fill = container.firstElementChild!.firstElementChild as HTMLElement;
        expect(fill.className).toContain("bg-brand-blue");
    });
});

describe("MobileNav", () => {
    beforeEach(() => mockPathname.mockReturnValue("/dashboard"));

    it("renders the primary nav destinations", () => {
        render(<MobileNav />);
        expect(screen.getByText("Home")).toBeInTheDocument();
        expect(screen.getByText("Classes")).toBeInTheDocument();
        expect(screen.getByText("Profile")).toBeInTheDocument();
    });

    it("highlights the link matching the current pathname", () => {
        mockPathname.mockReturnValue("/profile");
        render(<MobileNav />);
        const active = screen.getByText("Profile").closest("a") as HTMLElement;
        expect(active.className).toContain("text-brand-blue");
        const inactive = screen.getByText("Home").closest("a") as HTMLElement;
        expect(inactive.className).not.toContain("text-brand-blue");
    });
});

describe("Sidebar", () => {
    beforeEach(() => localStorage.clear());

    it("shows only student destinations for a student account", () => {
        storeUser({ id: 1, full_name: "Asha Rao", is_teacher: false });
        render(<Sidebar />);
        expect(screen.getByText("Dashboard")).toBeInTheDocument();
        expect(screen.getByText("Learn")).toBeInTheDocument();
        expect(screen.queryByText("Teacher")).not.toBeInTheDocument();
        expect(screen.queryByText("Analytics")).not.toBeInTheDocument();
        expect(screen.getByText("Student")).toBeInTheDocument();
        // Falls back to the first name / initial when there is no avatar
        expect(screen.getByText("Asha")).toBeInTheDocument();
        expect(screen.getByText("A")).toBeInTheDocument();
    });

    it("adds teacher destinations for a teacher account", () => {
        storeUser({ id: 2, full_name: "Ravi Kumar", is_teacher: true });
        render(<Sidebar />);
        expect(screen.getByText("Teacher")).toBeInTheDocument();
        expect(screen.getByText("Analytics")).toBeInTheDocument();
        expect(screen.getByText("Teacher Account")).toBeInTheDocument();
    });

    it("renders an avatar image when the user has a profile picture", () => {
        storeUser({ id: 3, full_name: "Pia", is_teacher: false, profile_pic: "avatars/pia.png" });
        render(<Sidebar />);
        const img = screen.getByAltText("U") as HTMLImageElement;
        expect(img.src).toContain("/auth/avatars/pia.png");
    });

    it("degrades gracefully with no stored user", () => {
        render(<Sidebar />);
        expect(screen.getByText("User")).toBeInTheDocument();
        expect(screen.getByText("U")).toBeInTheDocument();
    });
});

describe("TopicsToReview", () => {
    beforeEach(() => {
        localStorage.clear();
        vi.mocked(api.getLessons).mockReset();
    });

    afterEach(() => vi.restoreAllMocks());

    it("shows the empty state when there are no lessons", async () => {
        vi.mocked(api.getLessons).mockResolvedValue([]);
        render(<TopicsToReview />);
        expect(await screen.findByText("No topics assigned yet.")).toBeInTheDocument();
        expect(screen.queryByText("View All Topics")).not.toBeInTheDocument();
    });

    it("lists lessons, their topic, and a link to the practice quiz", async () => {
        vi.mocked(api.getLessons).mockResolvedValue([
            { id: 11, title: "Budget Cycles", topic: "budgeting", file_path: "a.pdf" },
            { id: 12, title: "Policy Memos", topic: "", file_path: "b.pdf" },
        ]);
        render(<TopicsToReview />);
        expect(await screen.findByText("Budget Cycles")).toBeInTheDocument();
        expect(screen.getByText("budgeting")).toBeInTheDocument();
        // Blank topics fall back to "General"
        expect(screen.getByText("General")).toBeInTheDocument();
        const quizLinks = screen.getAllByRole("link").filter((a) => a.getAttribute("href")?.startsWith("/quiz/"));
        expect(quizLinks.map((a) => a.getAttribute("href"))).toEqual(["/quiz/11", "/quiz/12"]);
        expect(screen.getByText("View All Topics")).toBeInTheDocument();
    });

    it("respects the limit prop", async () => {
        vi.mocked(api.getLessons).mockResolvedValue([
            { id: 1, title: "One", topic: "t", file_path: "" },
            { id: 2, title: "Two", topic: "t", file_path: "" },
            { id: 3, title: "Three", topic: "t", file_path: "" },
        ]);
        render(<TopicsToReview limit={2} />);
        expect(await screen.findByText("One")).toBeInTheDocument();
        expect(screen.getByText("Two")).toBeInTheDocument();
        expect(screen.queryByText("Three")).not.toBeInTheDocument();
    });

    it("opens the lesson file in a new tab when a row is clicked", async () => {
        const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
        vi.mocked(api.getLessons).mockResolvedValue([
            { id: 11, title: "Budget Cycles", topic: "budgeting", file_path: "a.pdf" },
        ]);
        render(<TopicsToReview />);
        await userEvent.click(await screen.findByText("Budget Cycles"));
        expect(openSpy).toHaveBeenCalledWith(expect.stringContaining("/lessons/11/file"), "_blank");
    });

    it("renders the empty state when the lessons request fails", async () => {
        const consoleSpy = vi.spyOn(console, "error").mockImplementation(() => {});
        vi.mocked(api.getLessons).mockRejectedValue(new Error("network down"));
        render(<TopicsToReview />);
        expect(await screen.findByText("No topics assigned yet.")).toBeInTheDocument();
        expect(consoleSpy).toHaveBeenCalled();
    });
});
