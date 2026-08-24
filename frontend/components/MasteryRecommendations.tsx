"use client";

import { useEffect, useState } from "react";
import { getToken, getUser } from "@/lib/api";

export function MasteryRecommendations() {
    const [mastery, setMastery] = useState<any[]>([]);
    const [recommendations, setRecommendations] = useState<any[]>([]);
    useEffect(() => {
        const user = getUser(); const token = getToken();
        if (!user || !token || user.is_teacher) return;
        const headers = { Authorization: `Bearer ${token}` };
        fetch(`http://127.0.0.1:5000/api/v1/students/${user.id}/mastery`, { headers }).then(r => r.ok ? r.json() : { mastery: [] }).then(d => setMastery(d.mastery || []));
        fetch(`http://127.0.0.1:5000/api/v1/students/${user.id}/recommendations`, { headers }).then(r => r.ok ? r.json() : { recommendations: [] }).then(d => setRecommendations(d.recommendations || []));
    }, []);
    if (!mastery.length && !recommendations.length) return null;
    return <section className="space-y-3"><h2 className="text-xl font-bold font-geist">Mastery and next steps</h2>
        <div className="grid md:grid-cols-2 gap-4"><div className="rounded-2xl border p-4">{mastery.map(item => <div key={item.competency_tag} className="mb-3"><div className="flex justify-between text-sm"><span>{item.competency_tag}</span><span>{Math.round(item.mastery * 100)}%</span></div><div className="h-2 bg-slate-100 rounded"><div className="h-2 bg-brand-blue rounded" style={{ width: `${item.mastery * 100}%` }} /></div></div>)}</div>
        <div className="rounded-2xl border p-4 space-y-2">{recommendations.map((item, index) => <a key={index} href={item.url || "#"} className="block text-sm text-brand-blue hover:underline">{item.title} — {item.reason}</a>)}</div></div></section>;
}
