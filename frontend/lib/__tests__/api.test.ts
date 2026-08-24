import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import api, { API_URL, storeToken, getToken, removeToken } from "@/lib/api";

function mockFetchOnce(body: unknown, init: Partial<Response> = {}) {
    const response = {
        ok: init.ok ?? true,
        status: init.status ?? 200,
        json: async () => body,
    } as Response;
    (global.fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValueOnce(response);
    return response;
}

describe("lib/api", () => {
    beforeEach(() => {
        global.fetch = vi.fn();
        localStorage.clear();
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    describe("login", () => {
        it("POSTs credentials to /auth/login and returns the parsed response", async () => {
            mockFetchOnce({ access_token: "abc123", id: 1, is_teacher: false });

            const result = await api.login("student@example.com", "hunter2");

            expect(global.fetch).toHaveBeenCalledTimes(1);
            const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
            expect(url).toBe(`${API_URL}/auth/login`);
            expect(options.method).toBe("POST");
            expect(options.headers).toMatchObject({ "Content-Type": "application/json" });
            expect(JSON.parse(options.body)).toEqual({
                email: "student@example.com",
                password: "hunter2",
            });
            expect(result).toEqual({ access_token: "abc123", id: 1, is_teacher: false });
        });

        it("throws and clears stored auth on a 401 response", async () => {
            storeToken("stale-token");
            mockFetchOnce({ msg: "Invalid credentials" }, { ok: false, status: 401 });

            await expect(api.login("student@example.com", "wrong")).rejects.toThrow(
                "Invalid credentials"
            );
            expect(getToken()).toBeNull();
        });
    });

    describe("getRecentQuizzes", () => {
        it("GETs /quizzes/recent with an Authorization header when a token is stored", async () => {
            storeToken("my-jwt");
            mockFetchOnce([{ id: 1, title: "Budgeting Basics" }]);

            const result = await api.getRecentQuizzes();

            expect(global.fetch).toHaveBeenCalledTimes(1);
            const [url, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
            expect(url).toBe(`${API_URL}/quizzes/recent`);
            expect(options.method).toBe("GET");
            expect(options.headers).toMatchObject({ Authorization: "Bearer my-jwt" });
            expect(result).toEqual([{ id: 1, title: "Budgeting Basics" }]);
        });

        it("omits the Authorization header when no token is stored", async () => {
            removeToken();
            mockFetchOnce([]);

            await api.getRecentQuizzes();

            const [, options] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
            expect(options.headers).not.toHaveProperty("Authorization");
        });
    });
});
