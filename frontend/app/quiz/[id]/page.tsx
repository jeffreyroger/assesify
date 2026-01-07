"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { X, Heart, Flag, Loader2 } from "lucide-react";
import { ProgressBar } from "@/components/ProgressBar";
import { Button } from "@/components/Button";
import { clsx } from "clsx";

interface Question {
    question: string;
    answer: string;
    options: string[];
    correct_answer: string;
    hint: string;
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

    useEffect(() => {
        if (!quizId) return;

        // Fetch quiz by ID
        fetch(`http://127.0.0.1:5000/api/quizzes/${quizId}`)
            .then(res => res.json())
            .then(data => {
                if (data.questions && Array.isArray(data.questions)) {
                    // Filter or validate questions if needed
                    setQuestions(data.questions);
                }
                setLoading(false);
            })
            .catch(err => {
                console.error("Failed to fetch quiz", err);
                setLoading(false);
            });
    }, []);

    const submitQuiz = async (finalStats: { correct: number }) => {
        try {
            await fetch(`http://127.0.0.1:5000/api/quizzes/${quizId}/submit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    user_id: 1, // hardcoded for demo
                    answers: questions.map((q, i) => ({
                        question: q.question,
                        answer: "Submitted via API",
                        is_correct: i < finalStats.correct // Approximated
                    }))
                })
            });
        } catch (e) {
            console.error("Failed to submit quiz", e);
        }
    };

    const handleCheck = () => {
        if (!selectedOption) return;

        const currentQ = questions[currentIndex];
        // Check if correct (case insensitive trim just in case)
        const isCorrect = selectedOption.trim() === currentQ.correct_answer?.trim();

        setStatus("review");
        if (isCorrect) {
            setStats(s => ({ xp: s.xp + 10, correct: s.correct + 1 }));
        }
    };

    const handleNext = () => {
        if (currentIndex < questions.length - 1) {
            setCurrentIndex(c => c + 1);
            setSelectedOption(null);
            setStatus("idle");
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
                            const isCorrect = opt === currentQuestion.correct_answer;
                            const showResult = status === 'review';

                            let variantClass = "border-slate-200 hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-zinc-800";

                            if (showResult) {
                                if (isCorrect) variantClass = "bg-brand-green/20 border-brand-green text-brand-green ring-0 shadow-[0_0_20px_rgba(34,197,94,0.2)]";
                                else if (isSelected && !isCorrect) variantClass = "bg-brand-red/20 border-brand-red text-brand-red ring-0 shadow-[0_0_20px_rgba(239,68,68,0.2)]";
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
                                    <span className="text-xl font-bold flex items-center justify-between">
                                        <span>
                                            <span className="mr-3 text-slate-400 group-hover:text-slate-600">{String.fromCharCode(65 + idx)}</span>
                                            <span className="text-slate-700 dark:text-zinc-200">{opt}</span>
                                        </span>
                                        {showResult && isCorrect && <span className="text-brand-green">✓</span>}
                                        {showResult && isSelected && !isCorrect && <span className="text-brand-red">✕</span>}
                                    </span>
                                </button>
                            )
                        })}
                    </div>

                    <div className="flex justify-center mt-4">
                        <button
                            onClick={() => alert(`💡 Hint: ${currentQuestion.hint}`)}
                            className="flex items-center gap-2 text-slate-400 hover:text-brand-yellow font-bold text-sm transition-colors"
                        >
                            <span>Need a hint?</span>
                        </button>
                    </div>

                    {status === 'review' && (
                        <div className="p-6 bg-slate-50 dark:bg-zinc-800/50 border-2 border-dashed border-slate-200 dark:border-zinc-700 rounded-3xl animate-in slide-in-from-bottom-4">
                            <h3 className="text-sm font-black uppercase tracking-tighter text-slate-400 mb-2">Pedagogical Insight</h3>
                            <p className="text-lg font-medium text-slate-700 dark:text-zinc-300 leading-relaxed italic">
                                "{currentQuestion.answer}"
                            </p>
                        </div>
                    )}
                </div>
            </main>

            {/* Footer Interface */}
            <footer className={clsx(
                "p-6 border-t-2 border-slate-200 dark:border-slate-800 sticky bottom-0 transition-colors duration-300",
                status === 'review' ? (selectedOption === currentQuestion.correct_answer ? "bg-brand-green/10" : "bg-brand-red/10") : "bg-white dark:bg-zinc-900"
            )}>
                <div className="max-w-2xl mx-auto flex items-center justify-between">
                    {status === 'review' && (
                        <div className="hidden md:block">
                            {selectedOption === currentQuestion.correct_answer ? (
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
                                variant={selectedOption === currentQuestion.correct_answer ? "primary" : "danger"}
                                className={clsx("w-full md:w-40", selectedOption === currentQuestion.correct_answer && "bg-brand-green hover:bg-brand-green/90 border-brand-green-dark")}
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
