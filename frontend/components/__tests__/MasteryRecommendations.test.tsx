import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MasteryRecommendations } from "@/components/MasteryRecommendations";

function mockFetchSequence(masteryBody: unknown, recommendationsBody: unknown) {
    global.fetch = vi.fn((url: string) => {
        if (url.includes("/mastery")) {
            return Promise.resolve({ ok: true, json: async () => masteryBody } as Response);
        }
        if (url.includes("/recommendations")) {
            return Promise.resolve({ ok: true, json: async () => recommendationsBody } as Response);
        }
        return Promise.resolve({ ok: true, json: async () => ({}) } as Response);
    }) as unknown as typeof fetch;
}

describe("MasteryRecommendations", () => {
    beforeEach(() => {
        localStorage.clear();
        localStorage.setItem("token", "test-token");
        localStorage.setItem("user", JSON.stringify({ id: 1, is_teacher: false }));
    });

    afterEach(() => {
        vi.restoreAllMocks();
    });

    it("renders nothing for a teacher account (no student mastery to show)", () => {
        localStorage.setItem("user", JSON.stringify({ id: 2, is_teacher: true }));
        mockFetchSequence({ mastery: [] }, { recommendations: [] });

        const { container } = render(<MasteryRecommendations />);

        expect(container).toBeEmptyDOMElement();
    });

    it("renders the mastery radar chart with the provided competency data", async () => {
        mockFetchSequence(
            {
                // Matches CompetencyMastery.to_dict(): updated_at is always
                // returned by GET /api/v1/students/:id/mastery.
                mastery: [
                    { competency_tag: "budgeting", mastery: 0.45, updated_at: "2026-08-20T10:00:00" },
                    { competency_tag: "policy-analysis", mastery: 0.82, updated_at: "2026-08-20T10:00:00" },
                ],
            },
            { recommendations: [] }
        );

        render(<MasteryRecommendations />);

        // PolarAngleAxis renders the competency tag as tick text in the SVG.
        expect(await screen.findByText("budgeting")).toBeInTheDocument();
        expect(await screen.findByText("policy-analysis")).toBeInTheDocument();
    });

    it("shows the Karmayogi-unavailable fallback banner when a recommendation has karmayogi_available: false", async () => {
        mockFetchSequence(
            { mastery: [] },
            {
                recommendations: [
                    // Matches karmayogi_service._internal_fallback(): score and
                    // source are always present on the wire.
                    {
                        competency_tag: "budgeting",
                        course_id: null,
                        title: "Remedial: Budgeting Basics",
                        reason: "Karmayogi is unavailable, showing an internal remedial quiz",
                        url: "/quiz/1",
                        score: 0.5,
                        source: "internal",
                        karmayogi_available: false,
                    },
                ],
            }
        );

        render(<MasteryRecommendations />);

        expect(
            await screen.findByText(/Karmayogi course catalog is unavailable/i)
        ).toBeInTheDocument();
        expect(screen.getByText(/Remedial: Budgeting Basics/)).toBeInTheDocument();
    });

    it("does not show the fallback banner when Karmayogi recommendations are available", async () => {
        mockFetchSequence(
            { mastery: [] },
            {
                recommendations: [
                    {
                        competency_tag: "budgeting",
                        course_id: "1",
                        title: "Public Finance 101",
                        reason: "Matches your budgeting gap",
                        url: "https://igotkarmayogi.gov.in/course/1",
                        score: 0.9,
                        source: "karmayogi",
                        karmayogi_available: true,
                    },
                ],
            }
        );

        render(<MasteryRecommendations />);

        await waitFor(() => {
            expect(screen.getByText(/Public Finance 101/)).toBeInTheDocument();
        });
        expect(
            screen.queryByText(/Karmayogi course catalog is unavailable/i)
        ).not.toBeInTheDocument();
    });
});
