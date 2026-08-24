"use client";

import { useEffect, useState } from "react";
import {
    Radar,
    RadarChart,
    PolarGrid,
    PolarAngleAxis,
    PolarRadiusAxis,
    ResponsiveContainer,
    Tooltip,
} from "recharts";
import { API_BASE_URL, getToken, getUser, MasteryResponse, RecommendationsResponse } from "@/lib/api";
import type { components } from "@/lib/api-types";

type MasteryRow = components["schemas"]["MasteryRow"];
type RecommendationItem = components["schemas"]["Recommendation"];

export function MasteryRecommendations() {
    const [mastery, setMastery] = useState<MasteryRow[]>([]);
    const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
    useEffect(() => {
        const user = getUser(); const token = getToken();
        if (!user || !token || user.is_teacher) return;
        const headers = { Authorization: `Bearer ${token}` };
        fetch(`${API_BASE_URL}/api/v1/students/${user.id}/mastery`, { headers })
            .then(r => r.ok ? r.json() : { mastery: [] })
            .then((d: MasteryResponse) => setMastery(d.mastery || []));
        fetch(`${API_BASE_URL}/api/v1/students/${user.id}/recommendations`, { headers })
            .then(r => r.ok ? r.json() : { recommendations: [] })
            .then((d: RecommendationsResponse) => setRecommendations(d.recommendations || []));
    }, []);
    if (!mastery.length && !recommendations.length) return null;
    const karmayogiDown = recommendations.some(item => item.karmayogi_available === false);
    return <section className="space-y-3"><h2 className="text-xl font-bold font-geist">Mastery and next steps</h2>
        {karmayogiDown && <div className="rounded-xl border-2 border-brand-yellow/40 bg-brand-yellow/10 px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-200">
            Karmayogi course catalog is unavailable right now — showing internal remedial quizzes instead.
        </div>}
        <div className="grid md:grid-cols-2 gap-4">
            <div className="rounded-2xl border p-4">
                <div className="h-72 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                        <RadarChart
                            data={mastery.map(item => ({
                                competency: item.competency_tag,
                                mastery: Math.round(item.mastery * 100),
                            }))}
                        >
                            <PolarGrid stroke="var(--color-slate-200, #e2e8f0)" />
                            <PolarAngleAxis dataKey="competency" tick={{ fontSize: 12 }} />
                            <PolarRadiusAxis angle={30} domain={[0, 100]} tick={{ fontSize: 10 }} />
                            <Tooltip formatter={(value) => [`${value}%`, "Mastery"]} />
                            <Radar
                                name="Mastery"
                                dataKey="mastery"
                                stroke="#1CB0F6"
                                fill="#1CB0F6"
                                fillOpacity={0.4}
                            />
                        </RadarChart>
                    </ResponsiveContainer>
                </div>
            </div>
            <div className="rounded-2xl border p-4 space-y-2">{recommendations.map((item, index) => <a key={index} href={item.url || "#"} className="block text-sm text-brand-blue hover:underline">{item.title} — {item.reason}</a>)}</div></div></section>;
}
