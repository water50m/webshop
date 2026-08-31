"use client";

import { CheckCircle2, ExternalLink, LoaderCircle, MessageCircle, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError, FacebookOnboardingPage } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function PageAvatar({ page }: { page: FacebookOnboardingPage }) {
  const initial = (page.name || "F").slice(0, 1).toUpperCase();
  const pictureUrl = `https://graph.facebook.com/v22.0/${encodeURIComponent(page.id)}/picture?type=large`;
  return (
    <span className="relative flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-full bg-[#e7f0ff] text-sm font-semibold text-[#1877f2]" aria-label={`รูปโปรไฟล์เพจ ${page.name}`}>
      {initial}
      {/* Facebook serves the current Page picture from its Graph endpoint; no image file is stored by SStore. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={pictureUrl} alt="" className="absolute inset-0 h-full w-full object-cover" onError={(event) => { event.currentTarget.style.display = "none"; }} />
    </span>
  );
}

export default function MyFacebookPagesPage() {
  const { user } = useAuth();
  const [pages, setPages] = useState<FacebookOnboardingPage[]>([]);
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const resultId = params.get("facebook_pages");
    const callbackError = params.get("facebook_error");
    if (callbackError) {
      const errorTimer = window.setTimeout(() => {
        setError(callbackError === "identity_mismatch" ? "บัญชี Facebook ที่ยืนยันไม่ตรงกับบัญชีที่ล็อกอินอยู่" : "ไม่สามารถตรวจสอบเพจ Facebook ได้");
      }, 0);
      window.history.replaceState({}, "", "/my-pages");
      return () => window.clearTimeout(errorTimer);
    }
    if (!user?.has_facebook_identity) return;
    const loadPages = resultId
      ? api.getFacebookAccountPages(resultId).then((result) => {
        setAttemptId(result.id);
        setPages(result.pages);
      })
      : api.listFacebookAccountPages().then((result) => {
        setAttemptId(null);
        setPages(result);
      });
    loadPages
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)))
      .finally(() => setBusy(false));
    if (resultId) window.history.replaceState({}, "", "/my-pages");
  }, [user?.has_facebook_identity]);

  async function checkFacebookPages() {
    setBusy(true);
    setError(null);
    try {
      const { authorization_url } = await api.startFacebookAccountPages();
      window.location.assign(authorization_url);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setBusy(false);
    }
  }

  async function registerPage(page: FacebookOnboardingPage) {
    if (!attemptId || page.registered) return;
    setBusy(true);
    setError(null);
    try {
      const registered = await api.registerFacebookAccountPage(attemptId, page.id);
      window.localStorage.setItem("active-shop-id", String(registered.shop_id));
      window.location.assign("/inbox");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
      setBusy(false);
    }
  }

  function activatePage(page: FacebookOnboardingPage) {
    if (!page.shop_id) {
      setError("เพจนี้ยังไม่มีร้านที่เชื่อมไว้ จึงยังไม่สามารถเปิดใช้งานได้");
      return;
    }
    window.localStorage.setItem("active-shop-id", String(page.shop_id));
    window.location.assign("/inbox");
  }

  if (!user?.has_facebook_identity) {
    return <main className="p-6 text-sm text-slate-600">หน้านี้ใช้ได้เฉพาะบัญชีที่ล็อกอินด้วย Facebook</main>;
  }

  return (
    <main className="w-full p-4 md:p-6">
      <section className="rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50 to-white p-5 shadow-sm">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-[#1877f2] p-2.5 text-white"><MessageCircle className="h-6 w-6" /></div>
          <div><h1 className="text-xl font-semibold text-slate-900">เพจ Facebook ของฉัน</h1><p className="mt-1 text-sm text-slate-600">เลือกเพจที่จะใช้งานเพื่อสลับ Inbox สินค้า ออเดอร์ และข้อมูลทั้งหมดไปยังเพจนั้น โดยแต่ละเพจเป็นร้านแยกกัน</p></div>
        </div>
        <button onClick={() => void checkFacebookPages()} disabled={busy} className="mt-5 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-[#1877f2] px-4 text-sm font-medium text-white hover:bg-[#166fe5] disabled:cursor-not-allowed disabled:opacity-60 sm:w-fit">{busy ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}ตรวจสอบเพจของฉัน</button>
      </section>

      {error && <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      {pages.length > 0 && <section className="mt-5 rounded-xl border border-slate-200 bg-white p-4"><h2 className="font-semibold text-slate-900">เพจที่ใช้งานได้</h2><ul className="mt-3 divide-y divide-slate-100">{pages.map((page) => <li key={page.id} className="flex flex-col gap-3 py-3 sm:flex-row sm:items-center sm:justify-between sm:gap-4"><div className="flex min-w-0 items-center gap-3"><PageAvatar page={page} /><div className="min-w-0"><p className="truncate font-medium text-slate-800">{page.name}</p><p className="text-xs text-slate-500">Page ID: {page.id}</p></div></div>{page.registered ? <div className="flex w-full items-center gap-3 sm:w-auto"><span className="hidden items-center gap-1 text-xs font-medium text-emerald-700 sm:inline-flex"><CheckCircle2 className="h-4 w-4" />ลงทะเบียนแล้ว</span><button onClick={() => activatePage(page)} className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-lg bg-[#1877f2] px-3 text-xs font-medium text-white hover:bg-[#166fe5] sm:w-auto"><MessageCircle className="h-3.5 w-3.5" />ใช้งานเพจนี้</button></div> : <button onClick={() => void registerPage(page)} disabled={busy} className="inline-flex h-9 w-full items-center justify-center gap-1.5 rounded-lg bg-violet-600 px-3 text-xs font-medium text-white hover:bg-violet-700 disabled:opacity-60 sm:w-auto"><ExternalLink className="h-3.5 w-3.5" />ลงทะเบียนเพจนี้</button>}</li>)}</ul></section>}
    </main>
  );
}
