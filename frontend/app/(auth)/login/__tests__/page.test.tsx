import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const pushMock = vi.fn();
vi.mock("next/navigation", () => ({
    useRouter: () => ({ push: pushMock }),
}));

const loginMock = vi.fn();
const storeTokenMock = vi.fn();
const storeUserMock = vi.fn();
vi.mock("@/lib/api", () => ({
    default: { login: (...args: unknown[]) => loginMock(...args) },
    storeToken: (...args: unknown[]) => storeTokenMock(...args),
    storeUser: (...args: unknown[]) => storeUserMock(...args),
}));

import LoginPage from "../page";

describe("Login page", () => {
    beforeEach(() => {
        pushMock.mockReset();
        loginMock.mockReset();
        storeTokenMock.mockReset();
        storeUserMock.mockReset();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("renders email and password fields and a submit button", () => {
        render(<LoginPage />);

        expect(screen.getByPlaceholderText(/joey@friends.com/i)).toBeInTheDocument();
        expect(screen.getByPlaceholderText("••••••••")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /log in/i })).toBeInTheDocument();
    });

    it("submits entered credentials to api.login, stores the token, and redirects on success", async () => {
        const user = userEvent.setup();
        loginMock.mockResolvedValueOnce({
            access_token: "jwt-abc",
            id: 1,
            is_teacher: false,
        });

        render(<LoginPage />);

        await user.type(screen.getByPlaceholderText(/joey@friends.com/i), "student@example.com");
        await user.type(screen.getByPlaceholderText("••••••••"), "hunter2");
        await user.click(screen.getByRole("button", { name: /log in/i }));

        await waitFor(() => {
            expect(loginMock).toHaveBeenCalledWith("student@example.com", "hunter2");
        });
        expect(storeTokenMock).toHaveBeenCalledWith("jwt-abc");
        expect(storeUserMock).toHaveBeenCalled();
        expect(pushMock).toHaveBeenCalledWith("/dashboard");
    });

    it("shows an error message and does not redirect when login fails", async () => {
        const user = userEvent.setup();
        loginMock.mockRejectedValueOnce(new Error("Invalid credentials"));

        render(<LoginPage />);

        await user.type(screen.getByPlaceholderText(/joey@friends.com/i), "student@example.com");
        await user.type(screen.getByPlaceholderText("••••••••"), "wrongpass");
        await user.click(screen.getByRole("button", { name: /log in/i }));

        expect(await screen.findByText("Invalid credentials")).toBeInTheDocument();
        expect(pushMock).not.toHaveBeenCalled();
    });
});
