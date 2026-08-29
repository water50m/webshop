"use client";

import { MessageCircle, ShieldCheck, UserMinus, UserPlus } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, ApiError, ChannelMember, FacebookConnection } from "@/lib/api";

const ROLE_LABEL: Record<ChannelMember["role"], string> = {
  page_owner: "เจ้าของเพจ",
  page_manager: "ผู้จัดการเพจ",
  page_staff: "พนักงานเพจ",
  viewer: "ดูอย่างเดียว",
};

export default function PageTeamPage() {
  const [channels, setChannels] = useState<FacebookConnection[]>([]);
  const [channelId, setChannelId] = useState<number | null>(null);
  const [members, setMembers] = useState<ChannelMember[]>([]);
  const [username, setUsername] = useState("");
  const [role, setRole] = useState<ChannelMember["role"]>("page_staff");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const loadMembers = useCallback(async (id: number | null) => {
    if (id === null) return setMembers([]);
    try {
      setError(null);
      setMembers(await api.listChannelMembers(id));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }, []);

  useEffect(() => {
    void api.listFacebookConnections().then((items) => {
      setChannels(items);
      setChannelId(items[0]?.id ?? null);
    }).catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadMembers(channelId), 0);
    return () => window.clearTimeout(timer);
  }, [channelId, loadMembers]);

  async function restartFacebookOnboarding() {
    setBusy(true);
    setError(null);
    try {
      window.location.assign((await api.startFacebookLogin()).authorization_url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "ไม่สามารถเริ่ม Facebook Login ได้");
      setBusy(false);
    }
  }

  async function addMember(event: FormEvent) {
    event.preventDefault();
    if (channelId === null || !username.trim()) return;
    setBusy(true);
    try {
      setError(null);
      const user = await api.findChannelShopUser(channelId, username.trim());
      await api.grantChannelMember(channelId, user.id, role);
      setUsername("");
      await loadMembers(channelId);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally { setBusy(false); }
  }

  async function changeRole(member: ChannelMember, nextRole: ChannelMember["role"]) {
    if (channelId === null) return;
    setBusy(true);
    try { await api.grantChannelMember(channelId, member.user_id, nextRole); await loadMembers(channelId); }
    catch (err) { setError(err instanceof ApiError ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  async function removeMember(member: ChannelMember) {
    if (channelId === null || !window.confirm(`ถอนสิทธิ์ ${member.display_name || member.username} จากเพจนี้หรือไม่?`)) return;
    setBusy(true);
    try { await api.revokeChannelMember(channelId, member.user_id); await loadMembers(channelId); }
    catch (err) { setError(err instanceof ApiError ? err.message : String(err)); }
    finally { setBusy(false); }
  }

  return <main className="mx-auto max-w-3xl p-4 md:p-6">
    <div className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50 to-white p-5 shadow-sm">
      <div className="flex gap-3"><span className="rounded-xl bg-indigo-600 p-2.5 text-white"><ShieldCheck className="h-6 w-6" /></span><div><h1 className="text-xl font-semibold text-slate-900">ทีมและสิทธิ์เพจ</h1><p className="mt-1 text-sm text-slate-600">กำหนดว่าผู้ใช้งานคนใดเห็นหรือตอบ Inbox ของแต่ละ Facebook Page ได้</p></div></div>
      {channels.length ? <select value={channelId ?? ""} onChange={(event) => setChannelId(event.target.value ? Number(event.target.value) : null)} className="mt-5 h-10 w-full rounded-lg border border-indigo-200 bg-white px-3 text-sm">
        {channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name || channel.page_id}</option>)}
      </select> : <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950"><p className="font-medium">ยังไม่มี Facebook Page ที่เข้าถึงได้</p><p className="mt-1 text-amber-900">ให้เข้าสู่ระบบ Facebook อีกครั้งเพื่อตรวจสิทธิ์ แล้วเลือก Page เพื่อลงทะเบียนหรือเปิดใช้งาน</p><button type="button" onClick={() => void restartFacebookOnboarding()} disabled={busy} className="mt-3 inline-flex h-10 items-center gap-2 rounded-lg bg-[#1877f2] px-4 text-sm font-medium text-white hover:bg-[#166fe5] disabled:cursor-not-allowed disabled:opacity-60"><MessageCircle className="h-4 w-4" />ดำเนินการต่อด้วย Facebook</button></div>}
    </div>
    {error && <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
    {channelId !== null && <form onSubmit={addMember} className="mt-5 rounded-xl border border-slate-200 bg-white p-4"><h2 className="font-semibold text-slate-900">เพิ่มสมาชิกเดิมในร้าน</h2><div className="mt-3 flex flex-col gap-2 sm:flex-row"><input value={username} onChange={(event) => setUsername(event.target.value)} placeholder="ชื่อผู้ใช้" className="h-10 flex-1 rounded-lg border border-slate-300 px-3 text-sm" /><select value={role} onChange={(event) => setRole(event.target.value as ChannelMember["role"])} className="h-10 rounded-lg border border-slate-300 px-3 text-sm"><option value="page_staff">พนักงานเพจ</option><option value="viewer">ดูอย่างเดียว</option><option value="page_manager">ผู้จัดการเพจ</option><option value="page_owner">เจ้าของเพจ</option></select><button disabled={busy} className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-indigo-600 px-4 text-sm font-medium text-white disabled:opacity-50"><UserPlus className="h-4 w-4" />เพิ่ม</button></div></form>}
    <section className="mt-5 rounded-xl border border-slate-200 bg-white p-4"><h2 className="font-semibold text-slate-900">สมาชิกเพจ</h2>{members.length ? <ul className="mt-3 divide-y divide-slate-100">{members.filter((member) => member.is_active).map((member) => <li key={member.user_id} className="flex flex-wrap items-center gap-3 py-3"><div className="min-w-36 flex-1"><p className="font-medium text-slate-800">{member.display_name || member.username}</p><p className="text-xs text-slate-500">{member.username}</p></div><select value={member.role} onChange={(event) => void changeRole(member, event.target.value as ChannelMember["role"])} disabled={busy || member.role === "page_owner"} className="h-9 rounded-lg border border-slate-300 px-2 text-xs disabled:opacity-60">{Object.entries(ROLE_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><button onClick={() => void removeMember(member)} disabled={busy || member.role === "page_owner"} className="inline-flex h-9 items-center gap-1 rounded-lg border border-rose-200 px-3 text-xs text-rose-700 disabled:opacity-50"><UserMinus className="h-3.5 w-3.5" />ถอน</button></li>)}</ul> : <p className="mt-3 text-sm text-slate-500">ยังไม่มีสมาชิก</p>}</section>
  </main>;
}
