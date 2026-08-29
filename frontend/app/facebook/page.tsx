"use client";

import { CheckCircle2, Link2, MessageCircle, RefreshCw, Trash2, Unplug } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError, FacebookConnection, FacebookPendingConnection } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function FacebookConnectionPage() {
  const { user } = useAuth();
  const [connections, setConnections] = useState<FacebookConnection[]>([]);
  const [pending, setPending] = useState<FacebookPendingConnection | null>(null);
  const [selectedPageId, setSelectedPageId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadConnections = async () => {
    if (user?.role !== "owner") return;
    try {
      setConnections(await api.listFacebookConnections());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  };

  useEffect(() => { void loadConnections(); }, [user?.role]);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const attemptId = params.get("facebook_connection");
    const callbackError = params.get("facebook_error");
    if (callbackError) {
      setError(callbackError === "cancelled" ? "ยกเลิกการเชื่อม Facebook แล้ว" : "Facebook ไม่สามารถเชื่อมต่อได้ กรุณาลองใหม่");
      window.history.replaceState({}, "", "/facebook");
      return;
    }
    if (!attemptId || user?.role !== "owner") return;
    setBusy(true);
    api.getPendingFacebookConnection(attemptId)
      .then((value) => {
        setPending(value);
        setSelectedPageId(value.pages[0]?.id ?? "");
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : String(err)))
      .finally(() => {
        setBusy(false);
        window.history.replaceState({}, "", "/facebook");
      });
  }, [user?.role]);

  async function beginConnection() {
    setBusy(true);
    setError(null);
    try {
      const { authorization_url } = await api.startFacebookConnection();
      window.location.assign(authorization_url);
    } catch (err) {
      setBusy(false);
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function selectPage() {
    if (!pending || !selectedPageId) return;
    setBusy(true);
    setError(null);
    try {
      const connection = await api.selectFacebookPage(pending.id, selectedPageId);
      setConnections((current) => [...current.filter((item) => item.id !== connection.id), connection]);
      setPending(null);
      setNotice(`เชื่อม ${connection.name || connection.page_id} สำเร็จแล้ว`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function disconnect(connection: FacebookConnection) {
    if (!window.confirm(`ยกเลิกการเชื่อม ${connection.name || connection.page_id} ใช่หรือไม่?`)) return;
    setBusy(true);
    setError(null);
    try {
      await api.disconnectFacebookPage(connection.id);
      setConnections((current) => current.filter((item) => item.id !== connection.id));
      setNotice(`ยกเลิกการเชื่อม ${connection.name || connection.page_id} แล้ว`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function deleteData(connection: FacebookConnection) {
    const label = connection.name || connection.page_id;
    if (!window.confirm(`ลบข้อมูลแชต ลูกค้า และออเดอร์ของ ${label} อย่างถาวรใช่หรือไม่? เพจอื่นจะไม่ถูกกระทบ และกู้คืนไม่ได้`)) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.deleteFacebookPageData(connection.id);
      setConnections((current) => current.filter((item) => item.id !== connection.id));
      setNotice(`ลบข้อมูลของ ${label} แล้ว รหัสยืนยัน: ${result.confirmation_code}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (user?.role !== "owner") {
    return <main className="p-6 text-sm text-slate-600">เฉพาะเจ้าของร้านเท่านั้นที่เชื่อม Facebook Page ได้</main>;
  }

  return (
    <main className="mx-auto max-w-3xl p-4 md:p-6">
      <div className="rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50 to-white p-5 shadow-sm">
        <div className="flex items-start gap-3">
          <div className="rounded-xl bg-[#1877f2] p-2.5 text-white"><MessageCircle className="h-6 w-6" /></div>
          <div>
            <h1 className="text-xl font-semibold text-slate-900">เชื่อม Facebook Page</h1>
            <p className="mt-1 text-sm text-slate-600">เจ้าของเพจล็อกอิน Facebook เพื่อเลือกเพจที่จะให้ระบบรับและตอบ Messenger</p>
          </div>
        </div>
        <button onClick={() => void beginConnection()} disabled={busy} className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-[#1877f2] px-4 text-sm font-medium text-white hover:bg-[#166fe5] disabled:cursor-not-allowed disabled:opacity-60"><Link2 className="h-4 w-4" />เชื่อม Facebook Page</button>
      </div>

      {error && <p className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">{error}</p>}
      {notice && <p className="mt-4 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-700"><CheckCircle2 className="h-4 w-4" />{notice}</p>}

      {pending && <section className="mt-5 rounded-xl border border-amber-200 bg-amber-50 p-4">
        <h2 className="font-semibold text-amber-950">เลือกเพจที่จะเชื่อม</h2>
        {pending.pages.length ? <><select value={selectedPageId} onChange={(event) => setSelectedPageId(event.target.value)} className="mt-3 h-10 w-full rounded-lg border border-amber-300 bg-white px-3 text-sm"><option value="" disabled>เลือก Facebook Page</option>{pending.pages.map((page) => <option key={page.id} value={page.id}>{page.name} {page.category ? `(${page.category})` : ""}</option>)}</select><button onClick={() => void selectPage()} disabled={busy || !selectedPageId} className="mt-3 inline-flex h-10 items-center gap-2 rounded-lg bg-amber-600 px-4 text-sm font-medium text-white hover:bg-amber-700 disabled:cursor-not-allowed disabled:opacity-60"><CheckCircle2 className="h-4 w-4" />ยืนยันการเชื่อมเพจ</button></> : <p className="mt-2 text-sm text-amber-900">ไม่พบเพจที่บัญชี Facebook นี้มีสิทธิ์จัดการ</p>}
      </section>}

      <section className="mt-5 rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between"><h2 className="font-semibold text-slate-900">เพจที่เชื่อมอยู่</h2><button onClick={() => void loadConnections()} disabled={busy} className="rounded p-2 text-slate-500 hover:bg-slate-100" aria-label="รีเฟรช"><RefreshCw className="h-4 w-4" /></button></div>
        {connections.length ? <ul className="mt-3 divide-y divide-slate-100">{connections.map((connection) => <li key={connection.id} className="flex items-center justify-between gap-3 py-3"><div><p className="font-medium text-slate-800">{connection.name || "Facebook Page"}</p><p className="text-xs text-slate-500">Page ID: {connection.page_id}</p></div><div className="flex items-center gap-2"><button onClick={() => void disconnect(connection)} disabled={busy} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-rose-200 px-3 text-xs font-medium text-rose-700 hover:bg-rose-50 disabled:cursor-not-allowed"><Unplug className="h-3.5 w-3.5" />ยกเลิก</button><button onClick={() => void deleteData(connection)} disabled={busy} className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-rose-300 px-3 text-xs font-medium text-rose-800 hover:bg-rose-50 disabled:cursor-not-allowed"><Trash2 className="h-3.5 w-3.5" />ลบข้อมูล</button></div></li>)}</ul> : <p className="mt-3 text-sm text-slate-500">ยังไม่มีเพจที่เชื่อมต่อ</p>}
      </section>
    </main>
  );
}
