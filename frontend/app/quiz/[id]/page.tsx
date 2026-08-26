"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { X, Heart, Flag, Loader2 } from "lucide-react";
import { ProgressBar } from "@/components/ProgressBar";
import { Button } from "@/components/Button";
import { clsx } from "clsx";
import { API_BASE_URL, StartAttemptResponse, getToken } from "@/lib/api";

interface Question {
    id?: string | number;
    question: string;
    /** Explanation. Only present for the owning-teacher view of the quiz. */
    answer?: string;
    options: string[];
    /** Only present for the owning-teacher view of the quiz; students receive
     *  it per-question from the /check endpoint after committing a selection. */
    correct_answer?: string;
    hint: string;
}

/** Server feedback for a single question, returned by
 *  POST /api/quizzes/:id/questions/:questionId/check once the student has
 *  committed a selection. This is the only way a student learns the answer. */
interface Feedback {
    is_correct: boolean;
    correct_answer?: string | null;
    explanation?: string | null;
}



export default function LearnPage() {
    const params = useParams();
    const quizId = params?.id;

    const [questions, setQuestions] = useState<Question[]>([]);
    const [currentIndex, setCurrentIndex] = useState(0);
    const [selectedOption, setSelectedOption] = useState<string | null>(null);
    const [status, setStatus] = useState<"idle" | "review" | "complete">("idle");
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState({ xp: 0, correct: 0 });
    const [attemptId, setAttemptId] = useState<number | null>(null);
    const [answersMap, setAnswersMap] = useState<Record<string, string>>({});
    const [savingMap, setSavingMap] = useState<Record<string, boolean>>({});
    // Per-question server feedback, populated only after the student checks.
    const [feedbackMap, setFeedbackMap] = useState<Record<string, Feedback>>({});

    useEffect(() => {
        if (!quizId) return;

        // Fetch quiz by ID
        fetch(`${API_BASE_URL}/api/quizzes/${quizId}`)
            .then(res => res.json())
            .then(async data => {
                if (data.questions && Array.isArray(data.questions)) {
                    setQuestions(data.questions);
                }
                setLoading(false);

                // Start an attempt so per-question answers can be autosaved.
                // This call is @jwt_required, so without the bearer token it
                // 401s and `attemptId` stays null - which is exactly what used
                // to happen, silently disabling autosave and the /check
                // feedback round-trip.
                const token = getToken();
                if (!token) return;
                try {
                    const resp = await fetch(`${API_BASE_URL}/api/v1/quizzes/${quizId}/attempts`, {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${token}`,
                        }
                    });
                    if (resp.ok) {
                        const j: StartAttemptResponse = await resp.json();
                        setAttemptId(j.id ?? null);
                    }
                } catch (e) {
                    // best-effort; continue without attemptId
                    console.warn('Could not start attempt for autosave', e);
                }
            })
            .catch(err => {
                console.error("Failed to fetch quiz", err);
                setLoading(false);
            });
    }, [quizId]);

    // Restore selected option when navigating between questions using answersMap
    useEffect(() => {
        const cur = questions[currentIndex];
        if (!cur) return;
        const qKey = cur.id ? String(cur.id) : String(currentIndex);
        const prev = answersMap[qKey];
        setSelectedOption(prev || null);
    }, [currentIndex, answersMap, questions]);

    // Keyboard navigation: Left = previous, Right/Enter = check/continue
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key === 'ArrowLeft') {
                if (currentIndex > 0) {
                    setCurrentIndex(c => c - 1);
                    setStatus('idle');
                }
            } else if (e.key === 'ArrowRight') {
                // If idle and an option is selected, act as Check
                if (status === 'idle' && selectedOption) {
                    handleCheck();
                } else {
                    // behave as Continue
                    handleNext();
                }
            } else if (e.key === 'Enter') {
                if (status === 'idle') {
                    handleCheck();
                } else {
                    handleNext();
                }
            }
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, [currentIndex, status, selectedOption, questions]);

    // Map a selected option's literal text back to its option key (A, B, C ...),
    // matching how the backend stores `Question.options[].key`.
    const optionKeyFor = (question: Question, selected: string | null): string | null => {
        if (!selected) return null;
        const idx = question.options ? question.options.indexOf(selected) : -1;
        return idx >= 0 ? String.fromCharCode(65 + idx) : null;
    };

    const submitQuiz = async (finalStats: { correct: number }) => {
        try {
            // Always the legacy submit endpoint, even when an attempt is open.
            // It is the score of record: it grades server-side from the stored
            // `correct_keys`, awards gamification (health/streak/diamonds) and
            // returns the body this app reads. It *reuses* the open attempt
            // rather than opening a second one, so the autosaved `responses`
            // rows end up attached to the scored attempt. Routing to
            // `/api/v1/<attempt>/submit` instead would score from a different
            // source and award no XP.
            const headers: Record<string, string> = { 'Content-Type': 'application/json' };
            const token = getToken();
            if (token) headers['Authorization'] = `Bearer ${token}`;

            await fetch(`${API_BASE_URL}/api/quizzes/${quizId}/submit`, {
                method: 'POST',
                headers,
                body: JSON.stringify({
                    user_id: 1, // hardcoded for demo
                    answers: questions.map((q, i) => {
                        const qKey = q.id ? String(q.id) : String(i);
                        const selected = answersMap[qKey] ?? null;
                        const key = optionKeyFor(q, selected);
                        return {
                            // Preferred: the server grades against the stored
                            // question and ignores the client's `is_correct`.
                            ...(q.id != null ? { question_id: q.id } : {}),
                            ...(key ? { selected_keys: [key] } : {}),
                            // Legacy fields kept alongside so a quiz with no
                            // relational questions still scores as before.
                            question: q.question,
                            answer: selected ?? "Submitted via API",
                            // Server feedback when we have it (the /check
                            // round-trip), else the old approximation. Ignored
                            // outright when question_id is present.
                            is_correct: feedbackMap[qKey]?.is_correct ?? (i < finalStats.correct)
                        };
                    })
                })
            });
        } catch (e) {
            console.error("Failed to submit quiz", e);
        }
    };

    const saveResponse = async (question: Question, selected: string): Promise<boolean> => {
        // persist locally
        const qKey = question.id ? String(question.id) : String(questions.indexOf(question));
        setAnswersMap(m => ({ ...m, [qKey]: selected }));

        // if we have attemptId and question.id, post to backend
        if (!attemptId || !question.id) return false;
        const key = optionKeyFor(question, selected) ?? selected;

        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        const token = getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;

        setSavingMap(m => ({ ...m, [qKey]: true }));
        try {
            const resp = await fetch(`${API_BASE_URL}/api/v1/attempts/${attemptId}/responses`, {
                method: 'POST',
                headers,
                body: JSON.stringify({ question_id: question.id, selected_keys: [key] })
            });
            return resp.ok;
        } catch (e) {
            console.warn('Autosave failed', e);
            return false;
        } finally {
            setSavingMap(m => ({ ...m, [qKey]: false }));
        }
    };

    // Ask the server to grade this one question and reveal its answer. The
    // quiz payload no longer carries `correct_answer`, so this round-trip is
    // what drives review-mode rendering. Falls back to a local comparison when
    // the question has no relational id or the request fails (e.g. a legacy
    // quiz served from the deprecated JSON blob, or an unauthenticated view).
    const fetchFeedback = async (question: Question, selected: string): Promise<Feedback> => {
        const localFallback: Feedback = {
            is_correct: question.correct_answer != null
                && selected.trim() === question.correct_answer.trim(),
            correct_answer: question.correct_answer,
            explanation: question.answer,
        };
        // Feedback is bound to the recorded answer in this student's attempt,
        // so without an attempt (anonymous, or a legacy quiz with no
        // relational questions) there is nothing to reveal.
        if (question.id == null || !attemptId) return localFallback;

        const headers: Record<string, string> = { 'Content-Type': 'application/json' };
        const token = getToken();
        if (token) headers['Authorization'] = `Bearer ${token}`;

        try {
            const resp = await fetch(
                `${API_BASE_URL}/api/quizzes/${quizId}/questions/${question.id}/check`,
                {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ attempt_id: attemptId }),
                }
            );
            if (!resp.ok) return localFallback;
            const j: Feedback = await resp.json();
            return {
                is_correct: Boolean(j.is_correct),
                correct_answer: j.correct_answer,
                explanation: j.explanation,
            };
        } catch (e) {
            console.warn('Could not fetch answer feedback', e);
            return localFallback;
        }
    };

    const handleCheck = async () => {
        if (!selectedOption) return;

        const currentQ = questions[currentIndex];
        const qKey = currentQ.id != null ? String(currentQ.id) : String(currentIndex);

        // Enter review mode immediately so the UI never stalls; the correct /
        // incorrect styling fills in as soon as the server answers.
        setStatus("review");

        // The autosave must land *before* asking for feedback: the /check
        // endpoint only reveals a question the student has actually answered
        // in this attempt.
        await saveResponse(currentQ, selectedOption);

        const feedback = await fetchFeedback(currentQ, selectedOption);
        setFeedbackMap(m => ({ ...m, [qKey]: feedback }));
        if (feedback.is_correct) {
            setStats(s => ({ xp: s.xp + 10, correct: s.correct + 1 }));
        }
    };

    const handleNext = () => {
        if (currentIndex < questions.length - 1) {
            setCurrentIndex(c => c + 1);
            setStatus("idle");
            // restore previously selected answer if any
            const nextQ = questions[currentIndex + 1];
            const qKey = nextQ && nextQ.id ? String(nextQ.id) : String(currentIndex + 1);
            const prev = answersMap[qKey];
            setSelectedOption(prev || null);
        } else {
            setStatus("complete");
            submitQuiz({ correct: stats.correct }); // Use current stats as last check was already added
        }
    };

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center bg-white dark:bg-zinc-900">
                <Loader2 className="w-8 h-8 animate-spin text-brand-blue" />
            </div>
        );
    }

    if (questions.length === 0) {
        return (
            <div className="min-h-screen flex flex-col items-center justify-center bg-white dark:bg-zinc-900 p-8 text-center bg-white dark:bg-zinc-900">
                <h1 className="text-2xl font-bold mb-4">No Quiz Found</h1>
                <p className="text-slate-500 mb-8">Could not load the quiz. Please try again later.</p>
                <Link href="/dashboard">
                    <Button>Return Home</Button>
                </Link>
            </div>
        )
    }

    if (status === "complete") {
        return (
            <div className="min-h-screen flex flex-col items-center justify-center bg-white dark:bg-black p-8 text-center animate-in zoom-in duration-500">
                <div className="space-y-8 max-w-md w-full">
                    <div className="space-y-4">
                        <div className="w-32 h-32 bg-brand-yellow rounded-full mx-auto flex items-center justify-center text-6xl shadow-xl shadow-brand-yellow/20 animate-bounce">
                            🏆
                        </div>
                        <h1 className="text-4xl font-bold font-geist text-slate-900 dark:text-white">
                            Lesson Complete!
                        </h1>
                        <p className="text-slate-500 text-lg">You've mastered this topic.</p>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-brand-blue p-6 rounded-2xl text-white shadow-lg border-b-4 border-brand-blue-dark">
                            <div className="mb-2 opacity-80 font-bold uppercase text-xs tracking-wider">Total XP</div>
                            <div className="text-4xl font-bold font-geist">+ {stats.xp}</div>
                        </div>
                        <div className="bg-brand-green p-6 rounded-2xl text-white shadow-lg border-b-4 border-brand-green-dark">
                            <div className="mb-2 opacity-80 font-bold uppercase text-xs tracking-wider">Correct</div>
                            <div className="text-4xl font-bold font-geist">{stats.correct}/{questions.length}</div>
                        </div>
                    </div>

                    <div className="pt-8">
                        <Link href="/dashboard">
                            <Button size="lg" className="w-full">
                                Continue
                            </Button>
                        </Link>
                    </div>
                </div>
            </div>
        );
    }

    const currentQuestion = questions[currentIndex];
    const currentKey = currentQuestion.id != null ? String(currentQuestion.id) : String(currentIndex);
    // Undefined until the /check round-trip for this question resolves.
    const currentFeedback = feedbackMap[currentKey];
    const progress = ((currentIndex) / questions.length) * 100;

    // Ensure we have options to display
    const hasOptions = currentQuestion.options && currentQuestion.options.length > 0;
    // Fallback for old data or failed generation
    const displayOptions = hasOptions ? currentQuestion.options : ["True", "False"];

    return (
        <div className="min-h-screen flex flex-col bg-white dark:bg-zinc-900">
            {/* Header */}
            <header className="p-6 max-w-5xl mx-auto w-full flex items-center justify-between gap-6">
                <Link href="/dashboard">
                    <X className="w-6 h-6 text-slate-400 hover:text-slate-600 cursor-pointer" />
                </Link>
                <ProgressBar value={progress} className="flex-1" />
                <div className="flex items-center gap-2 text-brand-red font-bold animate-pulse">
                    <Heart className="w-6 h-6 fill-current" />
                    <span>∞</span>
                </div>
            </header>

            {/* Question Content */}
            <main className="flex-1 max-w-2xl mx-auto w-full p-6 flex flex-col justify-center gap-8">
                <div className="space-y-6">
                    <h1 className="text-3xl md:text-3xl font-bold font-geist text-center text-slate-800 dark:text-slate-100 leading-tight">
                        {currentQuestion.question}
                    </h1>

                    <div className="grid grid-cols-1 gap-4 mt-8">
                        {displayOptions.map((opt, idx) => {
                            const isSelected = selectedOption === opt;
                            const isCorrect = currentFeedback?.correct_answer != null
                                && opt === currentFeedback.correct_answer;
                            // Hold off on the green/red reveal until the server
                            // has told us which option is correct.
                            const showResult = status === 'review' && currentFeedback !== undefined;

                            let variantClass = "border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-zinc-800";

                            if (showResult) {
                                if (isCorrect) variantClass = "bg-brand-green/20 border-brand-green text-brand-green ring-0";
                                else if (isSelected && !isCorrect) variantClass = "bg-brand-red/20 border-brand-red text-brand-red ring-0";
                                else if (!isSelected && !isCorrect) variantClass = "opacity-50";
                            } else if (isSelected) {
                                variantClass = "border-brand-blue-dark bg-brand-blue/10 ring-2 ring-brand-blue";
                            }

                            return (
                                <button
                                    key={idx}
                                    onClick={() => status === "idle" && setSelectedOption(opt)}
                                    disabled={status !== "idle"}
                                    className={clsx(
                                        "p-6 rounded-2xl border-2 border-b-4 text-left transition-all active:border-b-2 active:translate-y-[2px]",
                                        variantClass
                                    )}
                                >
                                    <span className="text-xl font-bold text-slate-700 dark:text-slate-200">{opt}</span>
                                </button>
                            )
                        })}
                    </div>

                    {status === 'review' && (currentFeedback?.explanation ?? currentQuestion.answer) && (
                        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-xl animate-in fade-in">
                            <p className="text-sm font-bold text-blue-600 dark:text-blue-400 mb-1">Explanation</p>
                            <p className="text-slate-700 dark:text-slate-300">{currentFeedback?.explanation ?? currentQuestion.answer}</p>
                        </div>
                    )}
                </div>
            </main>

            {/* Footer Interface */}
            <footer className={clsx(
                "p-6 border-t-2 border-slate-200 dark:border-slate-800 sticky bottom-0 transition-colors duration-300",
                status === 'review' && currentFeedback
                    ? (currentFeedback.is_correct ? "bg-brand-green/10" : "bg-brand-red/10")
                    : "bg-white dark:bg-zinc-900"
            )}>
                <div className="max-w-2xl mx-auto flex items-center justify-between">
                    {status === 'review' && currentFeedback && (
                        <div className="hidden md:block">
                            {currentFeedback.is_correct ? (
                                <div className="text-brand-green font-bold text-xl flex items-center gap-2">
                                    <div className="w-8 h-8 bg-brand-green rounded-full flex items-center justify-center text-white">✓</div>
                                    Correct!
                                </div>
                            ) : (
                                <div className="text-brand-red font-bold text-xl flex items-center gap-2">
                                    <div className="w-8 h-8 bg-brand-red rounded-full flex items-center justify-center text-white">✕</div>
                                    Incorrect
                                </div>
                            )}
                        </div>
                    )}

                    <div className="w-full md:w-auto ml-auto">
                        {status === "idle" ? (
                            <Button
                                className="w-full md:w-40"
                                size="lg"
                                onClick={handleCheck}
                                disabled={!selectedOption}
                            >
                                Check
                            </Button>
                        ) : (
                            <Button
                                variant={currentFeedback?.is_correct === false ? "danger" : "primary"}
                                className={clsx("w-full md:w-40", currentFeedback?.is_correct && "bg-brand-green hover:bg-brand-green/90 border-brand-green-dark")}
                                size="lg"
                                onClick={handleNext}
                            >
                                Continue
                            </Button>
                        )}
                    </div>
                </div>
            </footer>
        </div>
    );
}
