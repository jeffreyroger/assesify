import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import api, {
    API_BASE_URL,
    API_URL,
    storeToken,
    getToken,
    removeToken,
    storeUser,
    getUser,
} from "@/lib/api";

type FetchMock = ReturnType<typeof vi.fn>;

function mockFetchOnce(body: unknown, init: { ok?: boolean; status?: number } = {}) {
    (global.fetch as unknown as FetchMock).mockResolvedValueOnce({
        ok: init.ok ?? true,
        status: init.status ?? 200,
        json: async () => body,
    } as Response);
}

function lastCall() {
    const calls = (global.fetch as unknown as FetchMock).mock.calls;
    return calls[calls.length - 1] as [string, RequestInit & { headers: Record<string, string> }];
}

describe("lib/api token + user storage", () => {
    beforeEach(() => {
        localStorage.clear();
    });

    it("round-trips the auth token", () => {
        expect(getToken()).toBeNull();
        storeToken("jwt-1");
        expect(getToken()).toBe("jwt-1");
        removeToken();
        expect(getToken()).toBeNull();
    });

    it("round-trips the user object as JSON", () => {
        expect(getUser()).toBeNull();
        storeUser({ id: 7, full_name: "Asha" });
        expect(getUser()).toEqual({ id: 7, full_name: "Asha" });
    });

    it("removeToken clears the cached user too", () => {
        storeToken("jwt-1");
        storeUser({ id: 7 });
        removeToken();
        expect(getUser()).toBeNull();
    });

    it("derives API_URL from the configured base URL", () => {
        expect(API_URL).toBe(`${API_BASE_URL}/api`);
    });
});

describe("lib/api request wrappers", () => {
    beforeEach(() => {
        global.fetch = vi.fn();
        localStorage.clear();
        storeToken("jwt-token");
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("register POSTs the registration payload", async () => {
        mockFetchOnce({ msg: "User registered successfully" });
        await api.register({ email: "a@b.c", password: "pw", full_name: "A B", is_teacher: true });
        const [url, options] = lastCall();
        expect(url).toBe(`${API_URL}/auth/register`);
        expect(options.method).toBe("POST");
        expect(JSON.parse(options.body as string)).toEqual({
            email: "a@b.c",
            password: "pw",
            full_name: "A B",
            is_teacher: true,
        });
    });

    it("getClasses GETs the classes collection with auth", async () => {
        mockFetchOnce([{ id: 1, name: "Civics" }]);
        const result = await api.getClasses();
        const [url, options] = lastCall();
        expect(url).toBe(`${API_URL}/classes/`);
        expect(options.method).toBe("GET");
        expect(options.headers.Authorization).toBe("Bearer jwt-token");
        expect(result).toEqual([{ id: 1, name: "Civics" }]);
    });

    it("joinClass POSTs the join code", async () => {
        mockFetchOnce({ msg: "joined" });
        await api.joinClass("ABC123");
        const [url, options] = lastCall();
        expect(url).toBe(`${API_URL}/classes/join`);
        expect(JSON.parse(options.body as string)).toEqual({ code: "ABC123" });
    });

    it("createClass POSTs name and section", async () => {
        mockFetchOnce({ id: 2 });
        await api.createClass("Public Policy", "A");
        const [url, options] = lastCall();
        expect(url).toBe(`${API_URL}/classes/`);
        expect(options.method).toBe("POST");
        expect(JSON.parse(options.body as string)).toEqual({ name: "Public Policy", section: "A" });
    });

    it("inviteStudent prefers an explicitly passed token", async () => {
        mockFetchOnce({ msg: "invited" });
        await api.inviteStudent("explicit-token", { email: "s@x.y", full_name: "S" });
        const [url, options] = lastCall();
        expect(url).toBe(`${API_URL}/teacher/invite`);
        expect(options.headers.Authorization).toBe("Bearer explicit-token");
    });

    it("inviteStudent falls back to the stored token", async () => {
        mockFetchOnce({ msg: "invited" });
        await api.inviteStudent(null, { email: "s@x.y", full_name: "S" });
        expect(lastCall()[1].headers.Authorization).toBe("Bearer jwt-token");
    });

    it("updateProfile PUTs the changed fields", async () => {
        mockFetchOnce({ msg: "ok", user: { id: 1 } });
        await api.updateProfile({ full_name: "New Name", major: "Policy" });
        const [url, options] = lastCall();
        expect(url).toBe(`${API_URL}/auth/update-profile`);
        expect(options.method).toBe("PUT");
        expect(JSON.parse(options.body as string)).toEqual({ full_name: "New Name", major: "Policy" });
    });

    it("getProfile GETs the current user", async () => {
        mockFetchOnce({ id: 1, full_name: "Asha" });
        const user = await api.getProfile();
        expect(lastCall()[0]).toBe(`${API_URL}/auth/profile`);
        expect(user).toEqual({ id: 1, full_name: "Asha" });
    });

    it("uploadMaterial posts FormData without a Content-Type header", async () => {
        mockFetchOnce({ quiz_id: 3 });
        const form = new FormData();
        form.append("file", new Blob(["x"]), "notes.txt");
        await api.uploadMaterial(form);
        const [url, options] = lastCall();
        expect(url).toBe(`${API_URL}/teacher/materials`);
        // Letting the browser set the multipart boundary is the point here.
        expect(options.headers).not.toHaveProperty("Content-Type");
        expect(options.headers.Authorization).toBe("Bearer jwt-token");
        expect(options.body).toBe(form);
    });

    it("uploadAvatar posts FormData to the avatar endpoint", async () => {
        mockFetchOnce({ profile_pic: "avatars/a.png" });
        const form = new FormData();
        await api.uploadAvatar(form);
        const [url, options] = lastCall();
        expect(url).toBe(`${API_URL}/auth/upload-avatar`);
        expect(options.headers).not.toHaveProperty("Content-Type");
    });

    it("getLessons GETs the lessons collection", async () => {
        mockFetchOnce([]);
        await api.getLessons();
        expect(lastCall()[0]).toBe(`${API_URL}/lessons/`);
    });

    it("getWeeklyPerformance encodes its query string", async () => {
        mockFetchOnce({ topics: [] });
        await api.getWeeklyPerformance(42, "2026-08-01", "2026-08-07");
        expect(lastCall()[0]).toBe(
            `${API_URL}/quizzes/weekly-performance?user_id=42&start_date=2026-08-01&end_date=2026-08-07`
        );
    });

    it("generateWeeklyTest POSTs the generation parameters", async () => {
        mockFetchOnce({ id: 9 });
        await api.generateWeeklyTest(42, 10, "2026-08-01", "2026-08-07");
        const [url, options] = lastCall();
        expect(url).toBe(`${API_URL}/quizzes/generate-weekly-test`);
        expect(JSON.parse(options.body as string)).toEqual({
            user_id: 42,
            num_questions: 10,
            start_date: "2026-08-01",
            end_date: "2026-08-07",
        });
    });

    it("getTeacherAnalytics GETs the analytics endpoint", async () => {
        mockFetchOnce([]);
        await api.getTeacherAnalytics();
        expect(lastCall()[0]).toBe(`${API_URL}/teacher/analytics`);
    });
});

describe("lib/api error handling", () => {
    beforeEach(() => {
        global.fetch = vi.fn();
        localStorage.clear();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("surfaces the backend `msg` field as the thrown Error message", async () => {
        mockFetchOnce({ msg: "Email already registered" }, { ok: false, status: 400 });
        await expect(api.register({ email: "a@b.c", password: "p", full_name: "A" })).rejects.toThrow(
            "Email already registered"
        );
    });

    it("falls back to `message` then a generic string", async () => {
        mockFetchOnce({ message: "boom" }, { ok: false, status: 500 });
        await expect(api.getLessons()).rejects.toThrow("boom");

        mockFetchOnce({}, { ok: false, status: 500 });
        await expect(api.getLessons()).rejects.toThrow("API Error");
    });

    it("clears stored auth on a 422 (expired/invalid token) response", async () => {
        storeToken("stale");
        storeUser({ id: 1 });
        mockFetchOnce({ msg: "Invalid token" }, { ok: false, status: 422 });
        await expect(api.getProfile()).rejects.toThrow("Invalid token");
        expect(getToken()).toBeNull();
        expect(getUser()).toBeNull();
    });

    it("leaves stored auth intact on a non-auth error", async () => {
        storeToken("good");
        mockFetchOnce({ msg: "Not found" }, { ok: false, status: 404 });
        await expect(api.getProfile()).rejects.toThrow("Not found");
        expect(getToken()).toBe("good");
    });
});
