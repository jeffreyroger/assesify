"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { Button } from "@/components/Button";
import { getToken } from "@/lib/api";

export default function ResultsPage() {
    const { attemptId } = useParams<{ attemptId: string }>();
    const [result, setResult] = useState<any>(null);
    useEffect(() => {
        const token = getToken();
        fetch(`http://127.0.0.1:5000/api/v1/attempts/${attemptId}/result`, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
            .then(response => response.ok ? response.json() : Promise.reject())
            .then(setResult).catch(() => setResult({ feedback: [] }));
    }, [attemptId]);
    return <main className="max-w-3xl mx-auto p-8 space-y-6">
        <h1 className="text-3xl font-bold font-geist">Quiz results</h1>
        {result ? <>
            <p className="text-xl">Score: <strong>{result.score ?? "—"}%</strong></p>
            <div className="space-y-3">{result.feedback?.map((item: any) => <article key={item.question.id} className="border rounded-xl p-4">
                <p className="font-bold">{item.question.stem}</p>
                <p className={item.is_correct ? "text-brand-green" : "text-brand-red"}>{item.is_correct ? "Correct" : "Review this concept"}</p>
                <p className="text-slate-500">{item.question.explanation}</p>
            </article>)}</div>
        </> : <p>Loading feedback…</p>}
        <Link href="/dashboard"><Button>Back to dashboard</Button></Link>
    </main>;
}
