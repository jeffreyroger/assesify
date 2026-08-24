"use client";

import { Card } from "@/components/Card";
import { Button } from "@/components/Button";
import { Plus, Upload, Users, BarChart3, Folder, ChevronRight, MoreVertical } from "lucide-react";
import { useEffect, useState } from "react";
import { TeacherUploadModal } from "@/components/TeacherUploadModal";
import { CreateClassModal } from "@/components/CreateClassModal";
import api, { getToken } from "@/lib/api";
import Link from "next/link";

export default function TeacherDashboard() {
    const [isUploadOpen, setIsUploadOpen] = useState(false);
    const [isCreateClassOpen, setIsCreateClassOpen] = useState(false);
    const [selectedClassId, setSelectedClassId] = useState<string | null>(null);
    const [isInviteOpen, setIsInviteOpen] = useState(false);
    const [inviteEmail, setInviteEmail] = useState("");
    const [inviteName, setInviteName] = useState("");
    const [inviteMsg, setInviteMsg] = useState<string | null>(null);
    const [classes, setClasses] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(true);

    const fetchClasses = async () => {
        try {
            const data = await api.getClasses();
            // Filter only taught classes if getClasses returns both
            // Actually our backend fix now returns taught classes for teachers
            setClasses(data);
        } catch (err) {
            console.error("Failed to fetch classes", err);
        } finally {
            setIsLoading(false);
        }
    };

    useEffect(() => {
        fetchClasses();
    }, []);

    const handleUploadClick = (classCode: string, sectionId: string) => {
        // In a real app we'd track exactly which section
        setSelectedClassId(`${classCode}-${sectionId}`);
        setIsUploadOpen(true);
    };

    const handleInviteSubmit = async (e: React.FormEvent) => {
        e?.preventDefault();
        setInviteMsg(null);
        try {
            const token = getToken();
            if (!token) {
                setInviteMsg("You must be logged in as a teacher to invite students.");
                return;
            }
            const res = await api.inviteStudent(token, { email: inviteEmail, full_name: inviteName });
            setInviteMsg(res?.msg || "Invitation sent successfully");
            setInviteEmail("");
            setInviteName("");
            setIsInviteOpen(false);
        } catch (err: any) {
            setInviteMsg(err?.msg || err?.message || "Invite failed");
        }
    };

    return (
        <div className="space-y-8 pb-20">
            <TeacherUploadModal isOpen={isUploadOpen} onClose={() => setIsUploadOpen(false)} />
            <CreateClassModal
                isOpen={isCreateClassOpen}
                onClose={() => setIsCreateClassOpen(false)}
                onSuccess={fetchClasses}
            />

            {/* Header */}
            <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                <div>
                    <h1 className="text-3xl font-bold font-geist text-slate-900 dark:text-white">
                        Teacher Dashboard
                    </h1>
                    <p className="text-slate-500">Manage {classes.length} active classes.</p>
                </div>
                <div className="flex items-center gap-2">
                    <Button onClick={() => setIsInviteOpen((s) => !s)} variant={isInviteOpen ? "secondary" : undefined}>
                        Invite Student
                    </Button>
                    <Button onClick={() => setIsCreateClassOpen(true)}>
                        <Plus className="w-5 h-5 mr-2" />
                        Create New Class
                    </Button>
                </div>
            </div>

            {isInviteOpen && (
                <div className="bg-slate-50 dark:bg-zinc-900 p-6 rounded-lg border border-slate-200 dark:border-zinc-800">
                    <form className="grid grid-cols-1 md:grid-cols-3 gap-3 items-end" onSubmit={handleInviteSubmit}>
                        <div className="md:col-span-1">
                            <label className="text-sm font-bold text-slate-700 dark:text-slate-300">Full name</label>
                            <input value={inviteName} onChange={(e) => setInviteName(e.target.value)} className="w-full px-3 py-2 rounded-lg border-2 border-slate-200 dark:border-zinc-800" />
                        </div>
                        <div className="md:col-span-1">
                            <label className="text-sm font-bold text-slate-700 dark:text-slate-300">Email</label>
                            <input value={inviteEmail} onChange={(e) => setInviteEmail(e.target.value)} type="email" className="w-full px-3 py-2 rounded-lg border-2 border-slate-200 dark:border-zinc-800" />
                        </div>
                        <div className="md:col-span-1 flex items-center gap-2">
                            <Button type="submit">Send Invite</Button>
                            <Button variant="ghost" onClick={() => setIsInviteOpen(false)}>Cancel</Button>
                        </div>
                    </form>
                </div>
            )}

            {/* Rendered outside the collapsible form: a successful invite closes
                the form, and the result must still be visible. */}
            {inviteMsg && <p className="text-sm font-bold">{inviteMsg}</p>}

            {/* Overview Stats */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
                <Card className="p-4 flex flex-col gap-1" noPadding>
                    <span className="text-slate-500 text-xs font-bold uppercase">Total Students</span>
                    <span className="text-2xl font-bold font-geist">-</span>
                </Card>
                <Card className="p-4 flex flex-col gap-1" noPadding>
                    <span className="text-slate-500 text-xs font-bold uppercase">Active Quizzes</span>
                    <span className="text-2xl font-bold font-geist">-</span>
                </Card>
                <Card className="p-4 flex flex-col gap-1" noPadding>
                    <span className="text-slate-500 text-xs font-bold uppercase">Avg. Attendance</span>
                    <span className="text-2xl font-bold font-geist">-</span>
                </Card>
                <Card className="p-4 flex flex-col gap-1" noPadding>
                    <span className="text-slate-500 text-xs font-bold uppercase">Materials Uploaded</span>
                    <span className="text-2xl font-bold font-geist">-</span>
                </Card>
            </div>

            {/* Class Hierarchy */}
            <section className="space-y-6">
                {isLoading ? (
                    <div className="p-10 text-center text-slate-500">Loading classes...</div>
                ) : classes.length === 0 ? (
                    <div className="p-20 text-center border-2 border-dashed border-slate-200 rounded-2xl">
                        <p className="text-slate-500 mb-4 font-bold">You haven't created any classes yet.</p>
                        <Button onClick={() => setIsCreateClassOpen(true)}>Create Your First Class</Button>
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                        {classes.map((cls) => (
                            <Card key={cls.id} className="group hover:border-brand-blue transition-colors cursor-pointer p-6 relative overflow-hidden">
                                <div className={`absolute top-0 left-0 w-1 h-full ${cls.color || 'bg-brand-blue'}`}></div>
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <p className="text-[10px] font-black uppercase tracking-widest text-slate-400 mb-1">{cls.section}</p>
                                        <h3 className="font-bold font-geist text-xl flex items-center gap-2">
                                            {cls.name}
                                        </h3>
                                    </div>
                                    <span className="text-xs font-black text-slate-400 font-mono">{cls.code}</span>
                                </div>

                                <div className="flex items-center gap-4 text-sm text-slate-500 mb-6 font-bold">
                                    <span className="flex items-center gap-1"><Users className="w-4 h-4" /> - Students</span>
                                    <span className="flex items-center gap-1"><BarChart3 className="w-4 h-4" /> 0% Avg</span>
                                </div>

                                <div className="grid grid-cols-2 gap-2">
                                    <Button
                                        size="sm"
                                        variant="secondary"
                                        className="w-full font-bold"
                                        onClick={() => handleUploadClick(cls.code, cls.section)}
                                    >
                                        <Upload className="w-4 h-4 mr-2" /> Material
                                    </Button>
                                    <Link href={`/analytics?classId=${cls.id}`} className="w-full">
                                        <Button size="sm" variant="outline" className="w-full font-bold">
                                            Analytics
                                        </Button>
                                    </Link>
                                </div>
                            </Card>
                        ))}
                        {/* Add Section Button equivalent */}
                        <button
                            onClick={() => setIsCreateClassOpen(true)}
                            className="border-2 border-dashed border-slate-200 dark:border-slate-800 rounded-2xl flex flex-col items-center justify-center text-slate-400 font-bold hover:bg-slate-50 dark:hover:bg-zinc-900 hover:border-brand-blue transition-all min-h-[200px] gap-2"
                        >
                            <Plus className="w-8 h-8" />
                            <span>Create New Class</span>
                        </button>
                    </div>
                )}
            </section>
        </div>
    );
}

