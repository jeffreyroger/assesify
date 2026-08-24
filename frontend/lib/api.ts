import type { components, operations } from "./api-types";

export const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:5000";
export const API_URL = `${API_BASE_URL}/api`;

// Convenience aliases into the OpenAPI-generated schema (spec.md §7.3).
// These are typing-only; runtime behavior of every call site is unchanged.
export type User = components["schemas"]["User"];
export type LoginResponse = components["schemas"]["LoginResponse"];
export type RegisterRequest = components["schemas"]["RegisterRequest"];
export type UpdateProfileRequest = components["schemas"]["UpdateProfileRequest"];
export type RecentQuiz = components["schemas"]["RecentQuiz"];
export type Quiz = components["schemas"]["Quiz"];
export type Question = components["schemas"]["Question"];
export type StartAttemptResponse = components["schemas"]["StartAttemptResponse"];
export type SaveResponseRequest = components["schemas"]["SaveResponseRequest"];
export type SaveResponseResult = components["schemas"]["SaveResponseResult"];
export type SubmitAttemptResponse = components["schemas"]["SubmitAttemptResponse"];
export type AttemptResult = components["schemas"]["AttemptResult"];
export type MasteryResponse = components["schemas"]["MasteryResponse"];
export type GapsResponse = components["schemas"]["GapsResponse"];
export type RecommendationsResponse = components["schemas"]["RecommendationsResponse"];
export type ClassSummary = components["schemas"]["ClassSummary"];
type WeeklyPerformanceResponse =
    operations["getWeeklyPerformance"]["responses"]["200"]["content"]["application/json"];

export const storeToken = (token: string) => {
    if (typeof window !== "undefined") {
        localStorage.setItem("token", token);
    }
};

export const getToken = () => {
    if (typeof window !== "undefined") {
        return localStorage.getItem("token");
    }
    return null;
};

export const removeToken = () => {
    if (typeof window !== "undefined") {
        localStorage.removeItem("token");
        localStorage.removeItem("user");
    }
};

export const storeUser = (user: any) => {
    if (typeof window !== "undefined") {
        localStorage.setItem("user", JSON.stringify(user));
    }
};

export const getUser = () => {
    if (typeof window !== "undefined") {
        const userStr = localStorage.getItem("user");
        return userStr ? JSON.parse(userStr) : null;
    }
    return null;
};

const getHeaders = () => {
    const token = getToken();
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    return headers;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const handleResponse = async <T = any>(response: Response): Promise<T> => {
    if (!response.ok) {
        if (response.status === 401 || response.status === 422) {
            removeToken();
            if (typeof window !== "undefined") {
                window.location.href = "/login";
            }
        }
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.msg || errorData.message || "API Error");
    }
    return response.json();
};

const api = {
    login: async (email: string, password: string) => {
        const response = await fetch(`${API_URL}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        });
        return handleResponse<LoginResponse>(response);
    },

    register: async (data: RegisterRequest) => {
        const response = await fetch(`${API_URL}/auth/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(data),
        });
        return handleResponse(response);
    },

    getClasses: async () => {
        const response = await fetch(`${API_URL}/classes/`, {
            method: "GET",
            headers: getHeaders(),
        });
        return handleResponse<ClassSummary[]>(response);
    },

    joinClass: async (code: string) => {
        const response = await fetch(`${API_URL}/classes/join`, {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify({ code }),
        });
        return handleResponse(response);
    },

    // Temporary for testing
    createClass: async (name: string, section: string) => {
        const response = await fetch(`${API_URL}/classes/`, {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify({ name, section }),
        });
        return handleResponse(response);
    },

    inviteStudent: async (token: string | null, data: { email: string; full_name: string }) => {
        const t = token || getToken();
        const headers: Record<string,string> = { "Content-Type": "application/json" };
        if (t) headers["Authorization"] = `Bearer ${t}`;

        const response = await fetch(`${API_URL}/teacher/invite`, {
            method: "POST",
            headers,
            body: JSON.stringify(data),
        });
        return handleResponse(response);
    },

    updateProfile: async (data: UpdateProfileRequest) => {
        const response = await fetch(`${API_URL}/auth/update-profile`, {
            method: "PUT",
            headers: getHeaders(),
            body: JSON.stringify(data),
        });
        return handleResponse<{ msg: string; user: User }>(response);
    },

    getProfile: async () => {
        const response = await fetch(`${API_URL}/auth/profile`, {
            method: "GET",
            headers: getHeaders(),
        });
        return handleResponse<User>(response);
    },

    uploadMaterial: async (formData: FormData) => {
        const token = getToken();
        // Do not set Content-Type header for FormData, let browser set boundary
        const headers: Record<string,string> = {};
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const response = await fetch(`${API_URL}/teacher/materials`, {
            method: "POST",
            headers,
            body: formData,
        });
        return handleResponse(response);
    },

    getRecentQuizzes: async () => {
        const response = await fetch(`${API_URL}/quizzes/recent`, {
            method: "GET",
            headers: getHeaders(),
        });
        return handleResponse<RecentQuiz[]>(response);
    },

    getLessons: async () => {
        const response = await fetch(`${API_URL}/lessons/`, {
            method: "GET",
            headers: getHeaders(),
        });
        return handleResponse(response);
    },

    uploadAvatar: async (formData: FormData) => {
        const token = getToken();
        const headers: Record<string,string> = {};
        if (token) headers["Authorization"] = `Bearer ${token}`;

        const response = await fetch(`${API_URL}/auth/upload-avatar`, {
            method: "POST",
            headers,
            body: formData,
        });
        return handleResponse(response);
    },

    getWeeklyPerformance: async (userId: number, startDate: string, endDate: string) => {
        const response = await fetch(
            `${API_URL}/quizzes/weekly-performance?user_id=${userId}&start_date=${startDate}&end_date=${endDate}`,
            {
                method: "GET",
                headers: getHeaders(),
            }
        );
        return handleResponse<WeeklyPerformanceResponse>(response);
    },

    generateWeeklyTest: async (userId: number, numQuestions: number, startDate: string, endDate: string) => {
        const response = await fetch(`${API_URL}/quizzes/generate-weekly-test`, {
            method: "POST",
            headers: getHeaders(),
            body: JSON.stringify({
                user_id: userId,
                num_questions: numQuestions,
                start_date: startDate,
                end_date: endDate
            }),
        });
        return handleResponse(response);
    },

    getTeacherAnalytics: async () => {
        const response = await fetch(`${API_URL}/teacher/analytics`, {
            method: "GET",
            headers: getHeaders(),
        });
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        return handleResponse<any[]>(response);
    }
};

export default api;
