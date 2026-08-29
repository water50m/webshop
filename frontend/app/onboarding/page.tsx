"use client";

import { MessageCircle, LoaderCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api, ApiError, FacebookOnboardingPage } from "@/lib/api";

export default function OnboardingPage() {
  const params = useSearchParams();
  const router = useRouter();
  const attempt = params.get("facebook_login");
  const [pages, setPages] = useState<FacebookOnboardingPage[]>([]);
  const [selected, setSelected] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!attempt) { router.replace("/login"); return; }
    api.getFacebookLoginPending(attempt).then((data) => {
      setPages(data.pages); setSelected(data.pages[0]?.id ?? "");
    }).catch((err) => setError(err instanceof ApiError ? err.message : "ไม่สามารถตรวจสอบ Facebook Page ได้"))
      .finally(() => setBusy(false));
  }, [attempt, router]);

  async function continueWithPage() {
    if (!attempt || !selected) return;
    setBusy(true); setError("");
    try {
      const page = pages.find((item) => item.id === selected);
      const result = page?.registered ? await api.selectFacebookLoginPage(attempt, selected) : await api.registerFacebookLoginPage(attempt, selected);
      if (result.shop_id) window.localStorage.setItem("active-shop-id", String(result.shop_id));
      router.replace("/inbox");
    } catch (err) { setError(err instanceof ApiError ? err.message : "ดำเนินการไม่สำเร็จ"); setBusy(false); }
  }

  return <main className="min-h-screen bg-slate-100 p-4 flex items-center justify-center"><section className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-7 shadow-sm"><div className="flex items-center gap-3"><span className="rounded-xl bg-[#1877f2] p-2 text-white"><MessageCircle className="h-6 w-6" /></span><div><h1 className="font-semibold text-slate-900">ตั้งค่า Facebook Page</h1><p className="text-sm text-slate-500">เลือก Page ที่คุณมีสิทธิ์จัดการ</p></div></div>{busy && !pages.length && !error ? <div className="py-10 text-center text-sm text-slate-500"><LoaderCircle className="mx-auto mb-2 h-5 w-5 animate-spin" />กำลังตรวจสอบสิทธิ์…</div> : error ? <p className="mt-5 rounded-lg bg-rose-50 p-3 text-sm text-rose-700">{error}</p> : pages.length ? <><select className="mt-6 h-11 w-full rounded-lg border border-slate-300 px-3 text-sm" value={selected} onChange={(e) => setSelected(e.target.value)}>{pages.map((page) => <option key={page.id} value={page.id}>{page.name}{page.registered ? " — ใช้งานใน SStore แล้ว" : " — ลงทะเบียนร้านใหม่"}</option>)}</select><button onClick={() => void continueWithPage()} disabled={busy || !selected} className="mt-4 h-11 w-full rounded-lg bg-[#1877f2] text-sm font-medium text-white disabled:opacity-60">{busy ? "กำลังดำเนินการ…" : pages.find((page) => page.id === selected)?.registered ? "เปิด Inbox" : "ลงทะเบียน Page และเปิด Inbox"}</button></> : <div className="mt-6 rounded-lg bg-amber-50 p-4 text-sm text-amber-900">ไม่พบ Facebook Page ที่บัญชีนี้มีสิทธิ์จัดการ</div>}</section></main>;
}
