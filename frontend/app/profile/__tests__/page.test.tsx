import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ProfilePage from "@/app/profile/page";
import { storeUser, storeToken, getUser, getToken } from "@/lib/api";

const push = vi.fn();
vi.mock("next/navigation", () => ({
    useRouter: () => ({ push }),
    usePathname: () => "/profile",
    useParams: () => ({}),
}));

vi.mock("@/lib/api", async () => {
    const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
    return {
        ...actual,
        default: {
            ...actual.default,
            getProfile: vi.fn(),
            updateProfile: vi.fn(),
            uploadAvatar: vi.fn(),
            getLessons: vi.fn(),
        },
    };
});

import api from "@/lib/api";

const STUDENT = {
    id: 1,
    full_name: "Asha Rao",
    is_teacher: false,
    major: "Public Policy",
    location: "Delhi, India",
    streak: 6,
    diamonds: 30,
    health: 4,
};

beforeEach(() => {
    localStorage.clear();
    storeToken("jwt");
    vi.clearAllMocks();
    vi.mocked(api.getProfile).mockResolvedValue(STUDENT as never);
    vi.mocked(api.getLessons).mockResolvedValue([] as never);
});

afterEach(() => vi.restoreAllMocks());

describe("ProfilePage", () => {
    it("renders the fetched profile and caches it locally", async () => {
        render(<ProfilePage />);
        expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
        expect(screen.getByText(/Delhi, India/)).toBeInTheDocument();
        expect(screen.getByText("Public Policy")).toBeInTheDocument();
        await waitFor(() => expect(getUser()?.full_name).toBe("Asha Rao"));
    });

    it("shows student activity stats and achievements", async () => {
        render(<ProfilePage />);
        expect(await screen.findByText("Activity Stats")).toBeInTheDocument();
        expect(screen.getByText("6")).toBeInTheDocument();
        expect(screen.getByText("30")).toBeInTheDocument();
        expect(screen.getByText("❤️ 4")).toBeInTheDocument();
        expect(screen.getByText("Achievements")).toBeInTheDocument();
        expect(screen.getByText("Sharpshooter")).toBeInTheDocument();
    });

    it("hides student-only sections for a teacher", async () => {
        vi.mocked(api.getProfile).mockResolvedValue({ ...STUDENT, is_teacher: true } as never);
        render(<ProfilePage />);
        await screen.findByText("Asha Rao");
        expect(screen.queryByText("Activity Stats")).not.toBeInTheDocument();
        expect(screen.queryByText("Achievements")).not.toBeInTheDocument();
    });

    it("falls back to placeholders when fields are unset", async () => {
        vi.mocked(api.getProfile).mockResolvedValue({ id: 2, full_name: "Pat", is_teacher: false } as never);
        render(<ProfilePage />);
        expect(await screen.findByText(/Location not set/)).toBeInTheDocument();
        expect(screen.getByText(/Major not set/)).toBeInTheDocument();
    });

    it("renders cached data first when the profile request fails", async () => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        storeUser({ ...STUDENT, full_name: "Cached Name" });
        vi.mocked(api.getProfile).mockRejectedValue(new Error("offline"));
        render(<ProfilePage />);
        expect(await screen.findByText("Cached Name")).toBeInTheDocument();
    });

    it("edits and saves the profile", async () => {
        vi.mocked(api.updateProfile).mockResolvedValue({
            msg: "ok",
            user: { ...STUDENT, full_name: "Asha R. Rao", major: "Governance", location: "Pune" },
        } as never);
        render(<ProfilePage />);
        await userEvent.click(await screen.findByRole("button", { name: /edit profile/i }));

        const nameInput = screen.getByPlaceholderText("Full Name");
        await userEvent.clear(nameInput);
        await userEvent.type(nameInput, "Asha R. Rao");
        const majorInput = screen.getByPlaceholderText(/Major \/ Profession/i);
        await userEvent.clear(majorInput);
        await userEvent.type(majorInput, "Governance");
        const locationInput = screen.getByPlaceholderText(/Location/i);
        await userEvent.clear(locationInput);
        await userEvent.type(locationInput, "Pune");

        await userEvent.click(screen.getByRole("button", { name: /save changes/i }));

        await waitFor(() =>
            expect(api.updateProfile).toHaveBeenCalledWith({
                full_name: "Asha R. Rao",
                major: "Governance",
                location: "Pune",
            })
        );
        expect(await screen.findByText("Asha R. Rao")).toBeInTheDocument();
        expect(getUser()?.full_name).toBe("Asha R. Rao");
    });

    it("cancels editing without saving", async () => {
        render(<ProfilePage />);
        await userEvent.click(await screen.findByRole("button", { name: /edit profile/i }));
        await userEvent.clear(screen.getByPlaceholderText("Full Name"));
        await userEvent.type(screen.getByPlaceholderText("Full Name"), "Discarded");
        await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
        expect(api.updateProfile).not.toHaveBeenCalled();
        expect(screen.getByText("Asha Rao")).toBeInTheDocument();
    });

    it("alerts when saving fails", async () => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
        vi.mocked(api.updateProfile).mockRejectedValue(new Error("nope"));
        render(<ProfilePage />);
        await userEvent.click(await screen.findByRole("button", { name: /edit profile/i }));
        await userEvent.click(screen.getByRole("button", { name: /save changes/i }));
        await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to update profile"));
    });

    it("uploads a new avatar and shows it", async () => {
        vi.mocked(api.uploadAvatar).mockResolvedValue({ profile_pic: "avatars/new.png" } as never);
        render(<ProfilePage />);
        await screen.findByText("Asha Rao");
        const fileInput = document.getElementById("avatarInput") as HTMLInputElement;
        await userEvent.upload(fileInput, new File(["img"], "me.png", { type: "image/png" }));

        await waitFor(() => expect(api.uploadAvatar).toHaveBeenCalledTimes(1));
        const img = (await screen.findByAltText("Profile")) as HTMLImageElement;
        expect(img.src).toContain("/auth/avatars/new.png");
    });

    it("alerts when the avatar upload fails", async () => {
        vi.spyOn(console, "error").mockImplementation(() => {});
        const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => {});
        vi.mocked(api.uploadAvatar).mockRejectedValue(new Error("too big"));
        render(<ProfilePage />);
        await screen.findByText("Asha Rao");
        const fileInput = document.getElementById("avatarInput") as HTMLInputElement;
        await userEvent.upload(fileInput, new File(["img"], "me.png", { type: "image/png" }));
        await waitFor(() => expect(alertSpy).toHaveBeenCalledWith("Failed to upload avatar"));
    });

    it("logs the user out and redirects on Switch User", async () => {
        render(<ProfilePage />);
        await userEvent.click(await screen.findByRole("button", { name: /switch user/i }));
        expect(getToken()).toBeNull();
        expect(push).toHaveBeenCalledWith("/login");
    });

    it("renders the static class-performance breakdown", async () => {
        render(<ProfilePage />);
        expect(await screen.findByText("Intro to CS")).toBeInTheDocument();
        expect(screen.getByText("92%")).toBeInTheDocument();
        expect(screen.getByText("Adv. Calculus")).toBeInTheDocument();
    });
});
