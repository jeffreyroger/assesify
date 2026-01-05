export const API_URL = "http://127.0.0.1:5000/api";

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
    return {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
};

const handleResponse = async (response: Response) => {
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
        return handleResponse(response);
    },

    register: async (data: {
        email: string;
        full_name: string;
        password: string;
        is_teacher: boolean;
    }) => {
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
        return handleResponse(response);
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

    inviteStudent: async (token: string, data: { email: string; full_name: string }) => {
        const response = await fetch(`${API_URL}/teacher/invite`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify(data),
        });
        return handleResponse(response);
    },

    updateProfile: async (data: { full_name?: string; major?: string; location?: string }) => {
        const response = await fetch(`${API_URL}/auth/update-profile`, {
            method: "PUT",
            headers: getHeaders(),
            body: JSON.stringify(data),
        });
        return handleResponse(response);
    },

    getProfile: async () => {
        const response = await fetch(`${API_URL}/auth/profile`, {
            method: "GET",
            headers: getHeaders(),
        });
        return handleResponse(response);
    },

    uploadMaterial: async (formData: FormData) => {
        const token = getToken();
        // Do not set Content-Type header for FormData, let browser set boundary
        const headers: any = {};
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
        return handleResponse(response);
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
        const headers: any = {};
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
        return handleResponse(response);
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
        return handleResponse(response);
    }
};

export default api;
