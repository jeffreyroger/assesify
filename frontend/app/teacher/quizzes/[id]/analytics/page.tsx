"use client";

import { useParams } from "next/navigation";

export default function QuizAnalyticsPage() {
    const { id } = useParams<{ id: string }>();
    return <main className="max-w-4xl mx-auto p-8 space-y-6"><h1 className="text-3xl font-bold font-geist">Quiz analytics</h1>
        <p className="text-slate-500">Item analysis and misconception patterns for quiz {id} appear here as learners submit responses.</p>
        <div className="grid md:grid-cols-3 gap-4"><div className="rounded-xl border p-4">Item difficulty<br /><strong>Available after attempts</strong></div><div className="rounded-xl border p-4">Misconceptions<br /><strong>Available after attempts</strong></div><div className="rounded-xl border p-4">Competency gaps<br /><strong>Available after attempts</strong></div></div></main>;
}
