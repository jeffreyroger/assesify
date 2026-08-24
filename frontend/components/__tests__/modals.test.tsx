import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CreateClassModal } from "@/components/CreateClassModal";
import { JoinClassModal } from "@/components/JoinClassModal";
import { InviteStudentModal } from "@/components/InviteStudentModal";
import { storeToken } from "@/lib/api";

vi.mock("@/lib/api", async () => {
    const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    return {
        ...actual,
        default: {
            ...actual.default,
            createClass: vi.fn(),
            joinClass: vi.fn(),
            inviteStudent: vi.fn(),
        },
    };
});

import api from "@/lib/api";

beforeEach(() => {
    localStorage.clear();
    vi.mocked(api.createClass).mockReset();
    vi.mocked(api.joinClass).mockReset();
    vi.mocked(api.inviteStudent).mockReset();
});

afterEach(() => vi.restoreAllMocks());

describe("CreateClassModal", () => {
    it("renders nothing when closed", () => {
        const { container } = render(
            <CreateClassModal isOpen={false} onClose={vi.fn()} onSuccess={vi.fn()} />
        );
        expect(container).toBeEmptyDOMElement();
    });

    it("keeps submit disabled until both fields are filled", async () => {
        render(<CreateClassModal isOpen onClose={vi.fn()} onSuccess={vi.fn()} />);
        const submit = screen.getByRole("button", { name: /create class/i });
        expect(submit).toBeDisabled();
        await userEvent.type(screen.getByPlaceholderText(/Advanced Biology/i), "Public Policy");
        expect(submit).toBeDisabled();
        await userEvent.type(screen.getByPlaceholderText(/Semester 2/i), "A");
        expect(submit).toBeEnabled();
    });

    it("creates the class then fires onSuccess and onClose", async () => {
        const onSuccess = vi.fn();
        const onClose = vi.fn();
        vi.mocked(api.createClass).mockResolvedValue({ id: 1 });
        render(<CreateClassModal isOpen onClose={onClose} onSuccess={onSuccess} />);

        await userEvent.type(screen.getByPlaceholderText(/Advanced Biology/i), "Public Policy");
        await userEvent.type(screen.getByPlaceholderText(/Semester 2/i), "A");
        await userEvent.click(screen.getByRole("button", { name: /create class/i }));

        await waitFor(() => expect(api.createClass).toHaveBeenCalledWith("Public Policy", "A"));
        expect(onSuccess).toHaveBeenCalledTimes(1);
        expect(onClose).toHaveBeenCalledTimes(1);
    });

    it("shows the API error and stays open on failure", async () => {
        const onClose = vi.fn();
        vi.mocked(api.createClass).mockRejectedValue(new Error("Class name already used"));
        render(<CreateClassModal isOpen onClose={onClose} onSuccess={vi.fn()} />);

        await userEvent.type(screen.getByPlaceholderText(/Advanced Biology/i), "Dup");
        await userEvent.type(screen.getByPlaceholderText(/Semester 2/i), "A");
        await userEvent.click(screen.getByRole("button", { name: /create class/i }));

        expect(await screen.findByText("Class name already used")).toBeInTheDocument();
        expect(onClose).not.toHaveBeenCalled();
    });

    it("closes via the cancel button", async () => {
        const onClose = vi.fn();
        render(<CreateClassModal isOpen onClose={onClose} onSuccess={vi.fn()} />);
        await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
        expect(onClose).toHaveBeenCalledTimes(1);
    });
});

describe("JoinClassModal", () => {
    it("renders nothing when closed", () => {
        const { container } = render(<JoinClassModal isOpen={false} onClose={vi.fn()} onSuccess={vi.fn()} />);
        expect(container).toBeEmptyDOMElement();
    });

    it("upper-cases the entered code and submits it", async () => {
        const onSuccess = vi.fn();
        vi.mocked(api.joinClass).mockResolvedValue({ msg: "joined" });
        render(<JoinClassModal isOpen onClose={vi.fn()} onSuccess={onSuccess} />);

        const input = screen.getByPlaceholderText(/XY12Z3/i) as HTMLInputElement;
        await userEvent.type(input, "ab12c3");
        expect(input.value).toBe("AB12C3");

        await userEvent.click(screen.getByRole("button", { name: /join class/i }));
        await waitFor(() => expect(api.joinClass).toHaveBeenCalledWith("AB12C3"));
        expect(onSuccess).toHaveBeenCalledTimes(1);
    });

    it("surfaces a join failure", async () => {
        vi.mocked(api.joinClass).mockRejectedValue(new Error("Invalid class code"));
        render(<JoinClassModal isOpen onClose={vi.fn()} onSuccess={vi.fn()} />);
        await userEvent.type(screen.getByPlaceholderText(/XY12Z3/i), "BADCOD");
        await userEvent.click(screen.getByRole("button", { name: /join class/i }));
        expect(await screen.findByText("Invalid class code")).toBeInTheDocument();
    });
});

describe("InviteStudentModal", () => {
    it("renders nothing when closed", () => {
        const { container } = render(<InviteStudentModal isOpen={false} onClose={vi.fn()} />);
        expect(container).toBeEmptyDOMElement();
    });

    it("refuses to submit without a stored auth token", async () => {
        render(<InviteStudentModal isOpen onClose={vi.fn()} />);
        await userEvent.type(screen.getByPlaceholderText("Student Name"), "Sam");
        await userEvent.type(screen.getByPlaceholderText("student@example.com"), "sam@x.y");
        await userEvent.click(screen.getByRole("button", { name: /send invite/i }));
        expect(await screen.findByText(/Authentication token not found/i)).toBeInTheDocument();
        expect(api.inviteStudent).not.toHaveBeenCalled();
    });

    it("sends the invite and shows the success panel", async () => {
        storeToken("teacher-jwt");
        vi.mocked(api.inviteStudent).mockResolvedValue({ msg: "invited" });
        render(<InviteStudentModal isOpen onClose={vi.fn()} />);

        await userEvent.type(screen.getByPlaceholderText("Student Name"), "Sam Lee");
        await userEvent.type(screen.getByPlaceholderText("student@example.com"), "sam@x.y");
        await userEvent.click(screen.getByRole("button", { name: /send invite/i }));

        await waitFor(() =>
            expect(api.inviteStudent).toHaveBeenCalledWith("teacher-jwt", {
                email: "sam@x.y",
                full_name: "Sam Lee",
            })
        );
        expect(await screen.findByText("Invitation Sent!")).toBeInTheDocument();
    });

    it("shows an invite failure without the success panel", async () => {
        storeToken("teacher-jwt");
        vi.mocked(api.inviteStudent).mockRejectedValue(new Error("Email already registered"));
        render(<InviteStudentModal isOpen onClose={vi.fn()} />);

        await userEvent.type(screen.getByPlaceholderText("Student Name"), "Sam");
        await userEvent.type(screen.getByPlaceholderText("student@example.com"), "sam@x.y");
        await userEvent.click(screen.getByRole("button", { name: /send invite/i }));

        expect(await screen.findByText("Email already registered")).toBeInTheDocument();
        expect(screen.queryByText("Invitation Sent!")).not.toBeInTheDocument();
    });
});
