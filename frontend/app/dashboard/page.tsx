"use client";

import { useEffect, useState } from "react";
import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { ArrowRight, BookOpen, Clock, AlertCircle } from "lucide-react";
import Link from "next/link";
import { ProgressBar } from "@/components/ProgressBar";
import { JoinClassModal } from "@/components/JoinClassModal";
import { MasteryRecommendations } from "@/components/MasteryRecommendations";
import { CreateClassModal } from "@/components/CreateClassModal";
import { InviteStudentModal } from "@/components/InviteStudentModal";
import { TeacherUploadModal } from "@/components/TeacherUploadModal";
import { TopicsToReview } from "@/components/TopicsToReview";
import api, { getUser } from "@/lib/api";

export default function DashboardPage() {
    const [isJoinModalOpen, setIsJoinModalOpen] = useState(false);
    const [isCreateClassModalOpen, setIsCreateClassModalOpen] = useState(false);
    const [isInviteModalOpen, setIsInviteModalOpen] = useState(false);
    const [isUploadModalOpen, setIsUploadModalOpen] = useState(false);
    const [classes, setClasses] = useState<any[]>([]);
    const [lessons, setLessons] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [user, setUser] = useState<any>(null);

    const [recentQuizzes, setRecentQuizzes] = useState<any[]>([]);
    const [weeklyPerformance, setWeeklyPerformance] = useState<any>(null);
    const [isGeneratingWeeklyTest, setIsGeneratingWeeklyTest] = useState(false);

    const fetchClasses = async () => {
        try {
            const data = await api.getClasses();
            setClasses(data);
        } catch (err) {
            console.error("Failed to fetch classes", err);
        } finally {
            setIsLoading(false);
        }
    };

    const fetchLessons = async () => {
        try {
            const data = await api.getLessons();
            setLessons(data);
        } catch (err) {
            console.error("Failed to fetch lessons", err);
        }
    };

    const fetchRecentQuizzes = async () => {
        try {
            const data = await api.getRecentQuizzes();
            // Map to dashboard format
            const mapped = data.map((q: any) => ({
                id: q.id,
                class: q.topic || "General",
                title: q.title,
                due: "Flexible",
                duration: `${Math.max(5, q.questions_count * 2)} min`, // estimate duration
                priority: "medium"
            }));
            setRecentQuizzes(mapped);
        } catch (err) {
            console.error("Failed to fetch recent quizzes", err);
        }
    };

    const getWeekDates = () => {
        const now = new Date();
        const dayOfWeek = now.getDay();
        const startOfWeek = new Date(now);
        startOfWeek.setDate(now.getDate() - dayOfWeek); // Sunday
        startOfWeek.setHours(0, 0, 0, 0);

        const endOfWeek = new Date(startOfWeek);
        endOfWeek.setDate(startOfWeek.getDate() + 6); // Saturday
        endOfWeek.setHours(23, 59, 59, 999);

        return { startOfWeek, endOfWeek };
    };

    const fetchWeeklyPerformance = async () => {
        if (!user || user.is_teacher) return;

        const { startOfWeek, endOfWeek } = getWeekDates();
        try {
            const data = await api.getWeeklyPerformance(
                user.id,
                startOfWeek.toISOString().split('T')[0],
                endOfWeek.toISOString().split('T')[0]
            );
            setWeeklyPerformance(data);
        } catch (err) {
            console.error("Failed to fetch weekly performance", err);
        }
    };

    const handleGenerateWeeklyTest = async () => {
        if (!user) return;

        setIsGeneratingWeeklyTest(true);
        const { startOfWeek, endOfWeek } = getWeekDates();

        try {
            const quiz = await api.generateWeeklyTest(
                user.id,
                10, // 10 questions
                startOfWeek.toISOString().split('T')[0],
                endOfWeek.toISOString().split('T')[0]
            );

            // Redirect to the quiz
            window.location.href = `/quiz/${quiz.id}`;
        } catch (err: any) {
            console.error("Failed to generate weekly test", err);
            alert(err.message || "Failed to generate weekly test. Please try again.");
        } finally {
            setIsGeneratingWeeklyTest(false);
        }
    };

    useEffect(() => {
        const u = getUser();
        setUser(u);
        fetchClasses();
        fetchRecentQuizzes();
        fetchLessons();
        if (u && !u.is_teacher) {
            fetchWeeklyPerformance();
        }
    }, []);

    const pendingQuizzes = [
        { id: 2, class: "Advanced Biology", title: "Photosynthesis Quiz", due: "Tomorrow", duration: "15 min", priority: "high" },
        { id: 102, class: "Intro to CS", title: "Data Structures Basics", due: "3 days", duration: "20 min", priority: "medium" },
    ];

    return (
        <div className="max-w-6xl mx-auto space-y-12 pb-20">
            <JoinClassModal
                isOpen={isJoinModalOpen}
                onClose={() => setIsJoinModalOpen(false)}
                onSuccess={fetchClasses}
            />

            <CreateClassModal
                isOpen={isCreateClassModalOpen}
                onClose={() => setIsCreateClassModalOpen(false)}
                onSuccess={fetchClasses}
            />

            <InviteStudentModal
                isOpen={isInviteModalOpen}
                onClose={() => setIsInviteModalOpen(false)}
            />

            <TeacherUploadModal
                isOpen={isUploadModalOpen}
                onClose={() => {
                    setIsUploadModalOpen(false);
                    fetchLessons();
                    fetchRecentQuizzes();
                }}
            />

            {/* Welcome Section */}
            <div className="flex flex-col md:flex-row justify-between items-start gap-8 pt-10">
                <div className="flex-1">
                    <h1 className="text-4xl font-black font-geist text-slate-900 dark:text-white leading-tight">
                        Welcome back, <span className="text-brand-blue">{user?.full_name?.split(' ')[0] || 'User'}</span>! 👋
                    </h1>
                    <p className="text-slate-500 mt-2 font-medium">
                        {user?.is_teacher ? "Manage your classes and upload new study materials." : "You're doing great! Ready for today's challenges?"}
                    </p>
                </div>

                <div className="flex flex-col items-end gap-4 shrink-0">
                    {!user?.is_teacher && (
                        <div className="flex items-center gap-6 bg-white dark:bg-zinc-900 px-5 py-2 rounded-2xl border-2 border-slate-100 dark:border-slate-800 shadow-sm">
                            <div className="flex flex-col items-center">
                                <span className="text-lg font-black text-brand-orange leading-none">🔥 {user?.streak || 0}</span>
                                <span className="text-[9px] font-black text-slate-400 uppercase mt-1">Streak</span>
                            </div>
                            <div className="flex flex-col items-center">
                                <span className="text-lg font-black text-brand-blue leading-none">💎 {user?.diamonds || 0}</span>
                                <span className="text-[9px] font-black text-slate-400 uppercase mt-1">Gems</span>
                            </div>
                            <div className="flex flex-col items-center">
                                <span className="text-lg font-black text-brand-red leading-none">❤️ {user?.health || 5}</span>
                                <span className="text-[9px] font-black text-slate-400 uppercase mt-1">Life</span>
                            </div>
                        </div>
                    )}
                    <div className="flex gap-4 items-center">
                        {user?.is_teacher ? (
                            <>
                                <Button onClick={() => setIsUploadModalOpen(true)} className="bg-brand-purple hover:bg-brand-purple-dark text-white px-6 py-3 rounded-xl font-bold shadow-lg shadow-brand-purple/10">
                                    <ArrowRight className="w-5 h-5 mr-2" />
                                    Upload Topic
                                </Button>
                                <Button onClick={() => setIsCreateClassModalOpen(true)} variant="outline" className="px-6 py-3 rounded-xl border-2 font-bold hover:bg-slate-50 transition-colors">
                                    Create Class
                                </Button>
                                <Button onClick={() => setIsInviteModalOpen(true)} variant="ghost" className="text-slate-600 font-bold hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-zinc-800 rounded-xl px-4 py-3">
                                    Invite Student
                                </Button>
                            </>
                        ) : (
                            <Button onClick={() => setIsJoinModalOpen(true)} variant="outline" className="px-6 py-3 rounded-xl border-2 font-bold hover:bg-slate-50 transition-colors">
                                Join Class
                            </Button>
                        )}
                    </div>
                </div>
            </div>

            {/* Weekly Test Section (Students Only) */}
            {!user?.is_teacher && (
                <section className="mb-10">
                    <div className="bg-gradient-to-br from-brand-purple to-brand-blue p-8 rounded-3xl border-2 border-brand-purple-dark shadow-xl relative overflow-hidden">
                        {/* Background decoration */}
                        <div className="absolute top-0 right-0 w-64 h-64 bg-white/5 rounded-full -mr-32 -mt-32"></div>
                        <div className="absolute bottom-0 left-0 w-48 h-48 bg-white/5 rounded-full -ml-24 -mb-24"></div>

                        <div className="relative z-10">
                            <div className="flex items-start justify-between mb-6">
                                <div>
                                    <h2 className="text-2xl font-black text-white mb-2 flex items-center gap-2">
                                        📊 Weekly Test
                                    </h2>
                                    <p className="text-white/80 text-sm font-medium">
                                        {(() => {
                                            const { startOfWeek, endOfWeek } = getWeekDates();
                                            return `${startOfWeek.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} - ${endOfWeek.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`;
                                        })()}
                                    </p>
                                </div>
                                <div className="bg-white/20 backdrop-blur-sm px-4 py-2 rounded-xl">
                                    <span className="text-white font-black text-sm">10 Questions</span>
                                </div>
                            </div>

                            {weeklyPerformance && weeklyPerformance.topics && weeklyPerformance.topics.length > 0 ? (
                                <div className="space-y-4">
                                    <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-4">
                                        <h3 className="text-white font-bold text-sm mb-3 uppercase tracking-wide">Your Week at a Glance</h3>
                                        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                                            {weeklyPerformance.topics.slice(0, 6).map((topic: any, idx: number) => (
                                                <div key={idx} className="bg-white/10 rounded-xl p-3">
                                                    <div className="flex items-center justify-between mb-1">
                                                        <span className="text-white/90 text-xs font-bold truncate">{topic.topic}</span>
                                                        <span className={`text-xs font-black ${topic.accuracy >= 70 ? 'text-brand-green' :
                                                            topic.accuracy >= 50 ? 'text-brand-yellow' :
                                                                'text-brand-red'
                                                            }`}>
                                                            {topic.accuracy}%
                                                        </span>
                                                    </div>
                                                    <div className="w-full bg-white/20 rounded-full h-1.5">
                                                        <div
                                                            className={`h-1.5 rounded-full ${topic.accuracy >= 70 ? 'bg-brand-green' :
                                                                topic.accuracy >= 50 ? 'bg-brand-yellow' :
                                                                    'bg-brand-red'
                                                                }`}
                                                            style={{ width: `${topic.accuracy}%` }}
                                                        ></div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    <Button
                                        onClick={handleGenerateWeeklyTest}
                                        disabled={isGeneratingWeeklyTest}
                                        className="w-full bg-white text-brand-purple hover:bg-white/90 font-black py-4 rounded-xl shadow-lg text-lg"
                                    >
                                        {isGeneratingWeeklyTest ? (
                                            <><ArrowRight className="w-5 h-5 mr-2 animate-spin" /> Generating Your Test...</>
                                        ) : (
                                            <><ArrowRight className="w-5 h-5 mr-2" /> Generate Weekly Test</>
                                        )}
                                    </Button>
                                </div>
                            ) : (
                                <div className="bg-white/10 backdrop-blur-sm rounded-2xl p-6 text-center">
                                    <p className="text-white/80 mb-4">No quiz activity this week yet. Complete some quizzes to unlock your personalized weekly test!</p>
                                    <Button
                                        onClick={() => setIsJoinModalOpen(true)}
                                        variant="outline"
                                        className="border-white text-white hover:bg-white/20"
                                    >
                                        Browse Quizzes
                                    </Button>
                                </div>
                            )}
                        </div>
                    </div>
                </section>
            )}

            {/* Main Content Sections */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
                {/* Left Side: Quizzes & Topics */}
                <div className="space-y-10">
                    {/* Pending Quizzes */}
                    <section className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-xl font-bold font-geist flex items-center gap-2">
                                <AlertCircle className="w-5 h-5 text-brand-red" />
                                Action Required
                            </h2>
                        </div>
                        <div className="space-y-4">
                            {(recentQuizzes.length > 0 ? recentQuizzes : pendingQuizzes).slice(0, 2).map((quiz) => (
                                <div key={quiz.id} className="bg-white dark:bg-zinc-900 border-2 border-slate-200 dark:border-slate-800 rounded-2xl p-6 hover:border-brand-blue transition-all group shadow-sm">
                                    <div className="flex justify-between items-start mb-4">
                                        <div>
                                            <span className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1 block">{quiz.class}</span>
                                            <h3 className="text-lg font-bold font-geist group-hover:text-brand-blue transition-colors leading-tight">{quiz.title}</h3>
                                        </div>
                                        {quiz.priority === 'high' && <span className="text-[10px] font-black uppercase tracking-widest bg-brand-red/10 text-brand-red px-2 py-1 rounded-full">Urgent</span>}
                                    </div>
                                    <div className="flex items-center gap-4 text-xs font-bold text-slate-400 mb-6">
                                        <span className="flex items-center gap-1"><Clock className="w-3.5 h-3.5" /> {quiz.duration}</span>
                                        <span>• Due {quiz.due}</span>
                                    </div>
                                    <Link href={`/quiz/${quiz.id}`}>
                                        <Button className="w-full bg-slate-900 dark:bg-white dark:text-slate-900 text-white hover:opacity-90 transition-opacity rounded-xl">Start Quiz</Button>
                                    </Link>
                                </div>
                            ))}
                        </div>
                    </section>

                    {/* Topics to Review Integration */}
                    <section className="space-y-4">
                        <TopicsToReview limit={4} />
                    </section>
                </div>

                {/* Right Side: My Classes */}
                <div className="space-y-10">
                    <section className="space-y-4">
                        <h2 className="text-xl font-bold font-geist flex items-center gap-2">
                            <BookOpen className="w-5 h-5 text-brand-green" />
                            My Learning Spaces
                        </h2>
                        {isLoading ? (
                            <div className="text-slate-500 p-10 text-center bg-slate-50 dark:bg-zinc-800/50 rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-800">
                                Loading classes...
                            </div>
                        ) : classes.length === 0 ? (
                            <div className="text-center p-12 border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-3xl bg-slate-50/30">
                                <div className="w-16 h-16 bg-slate-100 dark:bg-zinc-800 rounded-3xl flex items-center justify-center mx-auto mb-4 text-slate-400">
                                    <BookOpen className="w-8 h-8" />
                                </div>
                                <p className="text-slate-500 font-medium mb-6">
                                    {user?.is_teacher
                                        ? "You haven't created any classes yet."
                                        : "You haven't joined any classes yet."}
                                </p>
                                <Button
                                    variant="outline"
                                    onClick={() => user?.is_teacher ? setIsCreateClassModalOpen(true) : setIsJoinModalOpen(true)}
                                    className="rounded-xl px-10 border-2"
                                >
                                    {user?.is_teacher ? "Create Class" : "Join Class"}
                                </Button>
                            </div>
                        ) : (
                            <div className="space-y-4">
                                {classes.map((cls) => (
                                    <Card key={cls.id} className="hover:-translate-y-1 transition-all duration-300 border-2 border-slate-200 dark:border-slate-800 shadow-sm" noPadding>
                                        <div className="flex gap-4 p-4">
                                            <div className={`w-20 h-20 rounded-2xl ${cls.color || 'bg-brand-blue'} shrink-0 flex items-center justify-center text-white font-black text-xl shadow-inner`}>
                                                {cls.name.charAt(0)}
                                            </div>
                                            <div className="flex-1 min-w-0 py-1">
                                                <div className="flex justify-between items-start">
                                                    <div>
                                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-0.5">{cls.section}</p>
                                                        <h3 className="text-lg font-bold font-geist text-slate-900 dark:text-white truncate">{cls.name}</h3>
                                                    </div>
                                                    <span className="text-[10px] font-black bg-brand-blue/10 text-brand-blue px-2 py-1 rounded-full whitespace-nowrap">0% Complete</span>
                                                </div>
                                                <div className="flex items-center justify-between mt-4">
                                                    <p className="text-xs font-bold text-slate-500 truncate">{cls.teacher}</p>
                                                    <Link href={`/class/${cls.id}`}>
                                                        <Button variant="ghost" size="sm" className="text-brand-blue font-black p-0 h-auto hover:bg-transparent">
                                                            Enter Class →
                                                        </Button>
                                                    </Link>
                                                </div>
                                            </div>
                                        </div>
                                    </Card>
                                ))}
                            </div>
                        )}
                    </section>
                </div>
            </div>
            {!user?.is_teacher && <MasteryRecommendations />}
        </div>
    );
}
