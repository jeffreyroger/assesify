import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
    useRouter: () => ({ push: pushMock }),
}));

const registerMock = vi.fn();
vi.mock("@/lib/api", () => ({
    default: { register: (...args: unknown[]) => registerMock(...args) },
}));

import RegisterPage from "../page";

describe("Register page", () => {
    beforeEach(() => {
        pushMock.mockReset();
        registerMock.mockReset();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("renders name, email, password, and teacher-checkbox fields", () => {
        render(<RegisterPage />);

        expect(screen.getByRole("button", { name: /sign up/i })).toBeInTheDocument();
        expect(screen.getByLabelText(/register as teacher/i)).toBeInTheDocument();
    });

    it("submits form data (including is_teacher) to api.register and redirects to /login on success", async () => {
        const user = userEvent.setup();
        registerMock.mockResolvedValueOnce({ msg: "ok" });
        const { container } = render(<RegisterPage />);

        const [nameInput, emailInput, passwordInput] = container.querySelectorAll("input");
        await user.type(nameInput, "Jamie Doe");
        await user.type(emailInput, "jamie@example.com");
        await user.type(passwordInput, "s3cret!");
        await user.click(screen.getByLabelText(/register as teacher/i));
        await user.click(screen.getByRole("button", { name: /sign up/i }));

        await waitFor(() => {
            expect(registerMock).toHaveBeenCalledWith({
                email: "jamie@example.com",
                full_name: "Jamie Doe",
                password: "s3cret!",
                is_teacher: true,
            });
        });
        expect(pushMock).toHaveBeenCalledWith("/login");
    });

    it("shows an error message and does not redirect when registration fails", async () => {
        const user = userEvent.setup();
        registerMock.mockRejectedValueOnce(new Error("Email already registered"));
        const { container } = render(<RegisterPage />);

        const [nameInput, emailInput, passwordInput] = container.querySelectorAll("input");
        await user.type(nameInput, "Jamie Doe");
        await user.type(emailInput, "jamie@example.com");
        await user.type(passwordInput, "s3cret!");
        await user.click(screen.getByRole("button", { name: /sign up/i }));

        expect(await screen.findByText("Email already registered")).toBeInTheDocument();
        expect(pushMock).not.toHaveBeenCalled();
    });
});
