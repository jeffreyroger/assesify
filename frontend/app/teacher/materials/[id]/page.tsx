"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/Button";
import { API_BASE_URL, getToken } from "@/lib/api";

export default function MaterialPage() {
    const { id } = useParams<{ id: string }>();
    const [status, setStatus] = useState("");
    const generate = async () => {
        setStatus("Generating MCQs…");
        const token = getToken();
        const response = await fetch(`${API_BASE_URL}/api/v1/materials/${id}/generate-quiz`, {
            method: "POST", headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
            body: JSON.stringify({ num_questions: 10, difficulty: "mixed", qtypes: ["mcq", "msq", "tf"], competency_tags: ["general"] }),
        });
        setStatus(response.ok ? "Quiz generated successfully." : "Unable to generate the quiz.");
    };
    return <main className="max-w-3xl mx-auto p-8 space-y-6"><h1 className="text-3xl font-bold font-geist">Material review</h1>
        <p className="text-slate-500">Configure and generate a reviewable MCQ quiz from this material.</p>
        <Button onClick={generate}>Generate MCQs</Button>{status && <p>{status}</p>}</main>;
}
