"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { ApiError, api, DataDeletionRequest } from "@/lib/api";
import { contactText, legal } from "../legal";

export default function DataDeletionPage() {
  const [pageId, setPageId] = useState("");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [result, setResult] = useState<DataDeletionRequest | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    if (!code) return;
    api.getFacebookDataDeletionRequest(code).then(setResult).catch((err) => setError(err instanceof ApiError ? err.message : String(err)));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true); setError(null); setResult(null);
    try {
      setResult(await api.createFacebookDataDeletionRequest({ page_id: pageId, requester_email: email, requester_name: name }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally { setBusy(false); }
  }

  return <main className="mx-auto max-w-3xl p-6 text-sm leading-7 text-slate-700">
    <h1 className="text-2xl font-bold text-slate-900">คำแนะนำการขอลบข้อมูล</h1>
    <p className="mt-3">{legal.businessName} ลบข้อมูลแยกตาม Facebook Page เสมอ การลบของเพจหนึ่งจะไม่กระทบข้อความ ลูกค้า หรือออเดอร์ของเพจอื่น</p>
    <h2 className="mt-7 text-lg font-semibold text-slate-900">สำหรับเจ้าของเพจที่เข้าสู่ระบบได้</h2>
    <p>เข้าสู่ SStore แล้วไปที่หน้า “เชื่อม Facebook Page” กด “ลบข้อมูล” ที่เพจของคุณ ยืนยันคำเตือน ระบบจะยกเลิกการเชื่อมต่อและลบข้อความ ลูกค้า บทสนทนา ออเดอร์ร่าง และประวัติแชตที่นำเข้าของเพจนั้นอย่างถาวรทันที</p>
    <h2 className="mt-7 text-lg font-semibold text-slate-900">สำหรับผู้ที่เข้าระบบไม่ได้</h2>
    <p>ส่งคำขอผ่านแบบฟอร์มนี้ เราจะยืนยันว่าผู้ขอมีสิทธิ์จัดการเพจก่อนจึงลบข้อมูลได้ อย่าส่ง Page Access Token หรือรหัสผ่านให้เรา</p>
    <form onSubmit={submit} className="mt-4 space-y-3 rounded-xl border border-slate-200 bg-white p-4">
      <label className="block">Page ID <input required value={pageId} onChange={(e) => setPageId(e.target.value)} className="mt-1 block h-10 w-full rounded border border-slate-300 px-3" /></label>
      <label className="block">ชื่อผู้ติดต่อ <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 block h-10 w-full rounded border border-slate-300 px-3" /></label>
      <label className="block">อีเมลติดต่อ <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="mt-1 block h-10 w-full rounded border border-slate-300 px-3" /></label>
      <button disabled={busy} className="rounded-lg bg-slate-900 px-4 py-2 font-medium text-white disabled:opacity-60">{busy ? "กำลังส่งคำขอ..." : "ส่งคำขอลบข้อมูล"}</button>
    </form>
    {error && <p className="mt-4 rounded-lg bg-rose-50 p-3 text-rose-700">{error}</p>}
    {result && <div className="mt-4 rounded-lg bg-emerald-50 p-3 text-emerald-800"><p>{result.detail}</p><p>รหัสติดตาม: <strong>{result.confirmation_code}</strong></p><p>สถานะ: {result.status}</p></div>}
    <h2 className="mt-7 text-lg font-semibold text-slate-900">การยกเลิกผ่าน Facebook</h2>
    <p>หากคุณลบแอปจากการตั้งค่า Facebook หรือ Meta ส่ง Data Deletion Callback ที่ลงนามถูกต้องมา ระบบจะลบข้อมูลเพจที่บัญชี Facebook นั้นเชื่อมไว้ และส่ง URL พร้อมรหัสยืนยันกลับให้ Meta ตรวจสอบสถานะได้</p>
    <p className="mt-6">หากต้องการความช่วยเหลือ ติดต่อ {contactText()}. อ่าน <Link href="/privacy" className="text-blue-700 underline">นโยบายความเป็นส่วนตัว</Link></p>
  </main>;
}
