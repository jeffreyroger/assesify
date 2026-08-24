"use client";

import { useState, useRef } from "react";
import { X, Upload, FileText, Check, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/Button";
import { ProgressBar } from "@/components/ProgressBar";
import { clsx } from "clsx";
import api from "@/lib/api";

interface TeacherUploadModalProps {
    isOpen: boolean;
    onClose: () => void;
    className?: string; // Class name or ID to attach to
}

export function TeacherUploadModal({ isOpen, onClose, className }: TeacherUploadModalProps) {
    const [step, setStep] = useState<"upload" | "config" | "generating" | "success">("upload");
    const [file, setFile] = useState<File | null>(null);
    const [dragActive, setDragActive] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    // Mock Config State
    const [config, setConfig] = useState({
        title: "",
        subject: "",
        difficulty: "medium",
        numQuestions: 10,
    });

    if (!isOpen) return null;

    const handleDrag = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.type === "dragenter" || e.type === "dragover") {
            setDragActive(true);
        } else if (e.type === "dragleave") {
            setDragActive(false);
        }
    };

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault();
        e.stopPropagation();
        setDragActive(false);
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            setFile(e.dataTransfer.files[0]);
        }
    };

    const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        e.preventDefault();
        if (e.target.files && e.target.files[0]) {
            setFile(e.target.files[0]);
        }
    };

    const handleGenerate = async () => {
        if (!file) return;

        setStep("generating");
        try {
            const formData = new FormData();
            formData.append("file", file);
            formData.append("title", config.title);
            formData.append("subject", config.subject);
            formData.append("difficulty", config.difficulty);
            formData.append("numQuestions", config.numQuestions.toString());

            await api.uploadMaterial(formData);
            setStep("success");
        } catch (err) {
            console.error("Upload failed", err);
            // Ideally show error state, for now just go back or stay
            setStep("config");
            alert("Failed to generate quiz. Please try again.");
        }
    };

    const reset = () => {
        setFile(null);
        setStep("upload");
        onClose();
    };

    return (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200">
            <div className="bg-white dark:bg-zinc-900 w-full max-w-lg rounded-3xl shadow-2xl border-2 border-slate-200 dark:border-slate-800 overflow-hidden flex flex-col max-h-[90vh]">
                {/* Header */}
                <div className="p-6 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center">
                    <h2 className="text-xl font-bold font-geist">Upload Materials</h2>
                    <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
                        <X className="w-6 h-6" />
                    </button>
                </div>

                {/* Content */}
                <div className="p-8 overflow-y-auto">
                    {step === "upload" && (
                        <div className="space-y-6">
                            <div
                                className={clsx(
                                    "border-4 border-dashed rounded-2xl p-10 flex flex-col items-center justify-center gap-4 transition-colors cursor-pointer",
                                    dragActive ? "border-brand-blue bg-brand-blue/5" : "border-slate-200 dark:border-slate-700 hover:border-brand-blue hover:bg-slate-50 dark:hover:bg-zinc-800"
                                )}
                                onDragEnter={handleDrag}
                                onDragLeave={handleDrag}
                                onDragOver={handleDrag}
                                onDrop={handleDrop}
                                onClick={() => inputRef.current?.click()}
                            >
                                <input
                                    ref={inputRef}
                                    type="file"
                                    className="hidden"
                                    onChange={handleChange}
                                    accept=".pdf,.txt,.docx"
                                />

                                {file ? (
                                    <>
                                        <div className="w-16 h-16 bg-brand-green/20 text-brand-green rounded-2xl flex items-center justify-center">
                                            <FileText className="w-8 h-8" />
                                        </div>
                                        <div className="text-center">
                                            <p className="font-bold text-lg text-slate-700 dark:text-slate-200">{file.name}</p>
                                            <p className="text-slate-500 text-sm">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                                        </div>
                                        <Button variant="ghost" className="text-brand-red hover:text-brand-red-dark hover:bg-brand-red/10" onClick={(e) => { e.stopPropagation(); setFile(null); }}>
                                            Remove
                                        </Button>
                                    </>
                                ) : (
                                    <>
                                        <div className="w-16 h-16 bg-slate-100 dark:bg-zinc-800 text-slate-400 rounded-2xl flex items-center justify-center">
                                            <Upload className="w-8 h-8" />
                                        </div>
                                        <div className="text-center space-y-1">
                                            <p className="font-bold text-lg text-slate-700 dark:text-slate-200">Click or Drag to Upload</p>
                                            <p className="text-slate-500 text-sm">PDF, DOCX, or TXT (Max 25MB)</p>
                                        </div>
                                    </>
                                )}
                            </div>

                            <Button disabled={!file} className="w-full" onClick={() => setStep("config")}>
                                Continue
                            </Button>
                        </div>
                    )}

                    {step === "config" && (
                        <div className="space-y-6">
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-1">Quiz Title</label>
                                    <input
                                        type="text"
                                        className="w-full p-3 rounded-xl border-2 border-slate-200 dark:border-slate-700 bg-transparent font-bold focus:border-brand-blue focus:outline-none"
                                        placeholder="e.g. Week 5 Assessment"
                                        value={config.title}
                                        onChange={(e) => setConfig({ ...config, title: e.target.value })}
                                    />
                                </div>

                                <div>
                                    <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-1">Subject / Topic</label>
                                    <input
                                        type="text"
                                        className="w-full p-3 rounded-xl border-2 border-slate-200 dark:border-slate-700 bg-transparent font-bold focus:border-brand-blue focus:outline-none"
                                        placeholder="e.g. Biology"
                                        value={config.subject}
                                        onChange={(e) => setConfig({ ...config, subject: e.target.value })}
                                    />
                                </div>

                                <div className="grid grid-cols-2 gap-4">
                                    <div>
                                        <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-1">Difficulty</label>
                                        <select
                                            className="w-full p-3 rounded-xl border-2 border-slate-200 dark:border-slate-700 bg-transparent font-bold focus:border-brand-blue focus:outline-none"
                                            value={config.difficulty}
                                            onChange={(e) => setConfig({ ...config, difficulty: e.target.value })}
                                        >
                                            <option value="easy">Easy</option>
                                            <option value="medium">Medium</option>
                                            <option value="hard">Hard</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="block text-sm font-bold text-slate-700 dark:text-slate-300 mb-1">Questions</label>
                                        <select
                                            className="w-full p-3 rounded-xl border-2 border-slate-200 dark:border-slate-700 bg-transparent font-bold focus:border-brand-blue focus:outline-none"
                                            value={config.numQuestions}
                                            onChange={(e) => setConfig({ ...config, numQuestions: parseInt(e.target.value) })}
                                        >
                                            <option value={5}>5 Questions</option>
                                            <option value={10}>10 Questions</option>
                                            <option value={15}>15 Questions</option>
                                            <option value={20}>20 Questions</option>
                                        </select>
                                    </div>
                                </div>
                            </div>

                            <div className="bg-brand-blue/10 p-4 rounded-xl flex items-start gap-3">
                                <Sparkles className="w-5 h-5 text-brand-blue shrink-0 mt-0.5" />
                                <p className="text-sm text-brand-blue-dark font-medium">
                                    AI will analyze your document and generate specific questions based on key concepts found in the text.
                                </p>
                            </div>

                            <div className="flex gap-3">
                                <Button variant="ghost" onClick={() => setStep("upload")} className="flex-1">Back</Button>
                                <Button onClick={handleGenerate} className="flex-1" disabled={!config.title || !config.subject}>
                                    Generate Quiz
                                </Button>
                            </div>
                        </div>
                    )}

                    {step === "generating" && (
                        <div className="flex flex-col items-center justify-center py-8 space-y-6 text-center">
                            <div className="relative">
                                <div className="w-24 h-24 border-4 border-slate-100 rounded-full"></div>
                                <div className="w-24 h-24 border-4 border-brand-blue border-t-transparent rounded-full animate-spin absolute top-0 left-0"></div>
                                <Sparkles className="w-8 h-8 text-brand-blue absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 animate-pulse" />
                            </div>
                            <div>
                                <h3 className="text-xl font-bold font-geist">Analyzing Materials...</h3>
                                <p className="text-slate-500">Extracting key concepts and generating questions.</p>
                            </div>
                        </div>
                    )}

                    {step === "success" && (
                        <div className="flex flex-col items-center justify-center py-8 space-y-6 text-center animate-in zoom-in duration-300">
                            <div className="w-24 h-24 bg-brand-green rounded-full flex items-center justify-center shadow-lg shadow-brand-green/20">
                                <Check className="w-12 h-12 text-white" />
                            </div>
                            <div>
                                <h3 className="text-2xl font-bold font-geist text-slate-900 dark:text-white">Quiz Generated!</h3>
                                <p className="text-slate-500">"{config.title}" has been assigned to the class.</p>
                            </div>
                            <div className="w-full bg-slate-50 dark:bg-zinc-800 p-4 rounded-xl border border-slate-200 dark:border-slate-700">
                                <div className="flex justify-between text-sm font-bold text-slate-500 mb-2">
                                    <span>Processing</span>
                                    <span>Complete</span>
                                </div>
                                <ProgressBar value={100} color="green" />
                            </div>
                            <Button onClick={reset} className="w-full">
                                Done
                            </Button>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
