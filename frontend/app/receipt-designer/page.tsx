"use client";

import { Check, ImagePlus, Palette, Printer, Save } from "lucide-react";
import { useEffect, useState } from "react";
import Receipt from "../components/Receipt";
import ReceiptTabs from "../components/ReceiptTabs";
import { api, ApiError, resolveImageUrl, Sale, ShopSettings } from "@/lib/api";

const SAMPLE_SALE: Sale = {
  id: 1001, receipt_no: 1001, status: "completed", payment_method: "cash", discount_amount: 10, paid_amount: 200, change_amount: 10,
  note: "ตัวอย่างหมายเหตุในบิล", created_by_name: "พนักงานหน้าร้าน", completed_at: "2026-08-30T10:30:00",
  items: [
    { id: 1, product_id: 1, product_name: "กาแฟเย็น", sku: "COF-01", quantity: 2, unit_price: 75, discount_amount: 0, refunded_quantity: 0, modifiers: [{ name: "หวานน้อย", price_delta: 0 }], line_total: 150 },
    { id: 2, product_id: 2, product_name: "ครัวซองต์", sku: "BAK-01", quantity: 1, unit_price: 50, discount_amount: 10, refunded_quantity: 0, modifiers: [], line_total: 40 },
  ],
  payments: [{ method: "cash", amount: 200 }], subtotal: 200, total_discount: 10, promotion_discount: 0, total: 190,
  customer_phone: "0812345678", customer_name: "ลูกค้าตัวอย่าง", points_earned: 1, points_redeemed: 0, customer_points_balance: 18,
};

export default function ReceiptDesignerPage() {
  const [settings, setSettings] = useState<ShopSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  function normalizeSettings(current: ShopSettings): ShopSettings {
    return {
      ...current,
      receipt_paper_width: current.receipt_paper_width === 58 ? 58 : 80,
      receipt_logo_url: current.receipt_logo_url ?? "",
      receipt_show_logo: current.receipt_show_logo ?? true,
      receipt_footer_text: current.receipt_footer_text ?? "ขอบคุณที่ใช้บริการ",
      receipt_show_cashier: current.receipt_show_cashier ?? true,
      receipt_show_member: current.receipt_show_member ?? true,
    };
  }

  useEffect(() => { api.getSettings().then((current) => setSettings(normalizeSettings(current))).catch((e) => setError(e instanceof ApiError ? e.message : String(e))); }, []);
  function update(patch: Partial<ShopSettings>) { setSettings((current) => current ? { ...current, ...patch } : current); setSaved(false); }
  async function save() {
    if (!settings) return;
    setSaving(true); setError(null);
    try { setSettings(normalizeSettings(await api.updateSettings(settings))); setSaved(true); }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setSaving(false); }
  }

  async function uploadLogo(file: File | undefined) {
    if (!file) return;
    setSaving(true); setError(null);
    try { setSettings(normalizeSettings(await api.uploadReceiptLogo(file))); setSaved(true); }
    catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setSaving(false); }
  }

  if (!settings) return <main className="p-6 text-slate-500">กำลังโหลดตัวอย่างใบเสร็จ...</main>;
  return <main className="w-full p-4 md:p-6 lg:p-8">
    <ReceiptTabs />
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-xl font-semibold flex items-center gap-2"><Palette className="w-5 h-5 text-amber-500" />ออกแบบใบเสร็จ</h1><p className="mt-1 text-sm text-slate-500">ปรับรูปแบบและดูผลลัพธ์ก่อนใช้กับใบเสร็จจริงของร้าน</p></div><div className="flex w-full gap-2 sm:w-auto"><button onClick={() => window.print()} className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 sm:flex-none"><Printer className="w-4 h-4" />พิมพ์ตัวอย่าง</button><button onClick={() => void save()} disabled={saving} className="inline-flex flex-1 items-center justify-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-white hover:bg-amber-600 disabled:opacity-50 sm:flex-none"><Save className="w-4 h-4" />{saving ? "กำลังบันทึก..." : "บันทึกแบบ"}</button></div></div>
    {error && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}{saved && <p className="mb-4 inline-flex items-center gap-1.5 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700"><Check className="w-4 h-4" />บันทึกรูปแบบใบเสร็จแล้ว</p>}
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px] print:block">
      <section className="space-y-4 print:hidden">
        <div className="rounded-xl border border-slate-200 bg-white p-4"><h2 className="font-medium mb-3">ขนาดกระดาษ</h2><div className="flex gap-3"><label className="flex items-center gap-2"><input type="radio" checked={settings.receipt_paper_width === 58} onChange={() => update({ receipt_paper_width: 58 })} />58 มม.</label><label className="flex items-center gap-2"><input type="radio" checked={settings.receipt_paper_width === 80} onChange={() => update({ receipt_paper_width: 80 })} />80 มม.</label></div><p className="mt-2 text-xs text-slate-500">เลือกให้ตรงกับขนาดม้วนกระดาษของเครื่องพิมพ์</p></div>
        <div className="rounded-xl border border-slate-200 bg-white p-4"><h2 className="font-medium mb-3">โลโก้ร้าน</h2><div className="flex items-center gap-3">{settings.receipt_logo_url ? <img src={resolveImageUrl(settings.receipt_logo_url) ?? undefined} alt="ตัวอย่างโลโก้ร้าน" className="h-16 w-16 rounded border object-contain p-1 grayscale contrast-150" /> : <div className="flex h-16 w-16 items-center justify-center rounded-full bg-slate-900 text-white"><ImagePlus className="w-5 h-5" /></div>}<label className="cursor-pointer rounded-lg border px-3 py-2 text-sm hover:bg-slate-50">เลือกรูป<input type="file" accept="image/png,image/jpeg,image/webp" className="hidden" onChange={(event) => void uploadLogo(event.target.files?.[0])} /></label></div><label className="mt-3 flex items-center justify-between gap-3"><span><span className="block text-sm font-medium">แสดงโลโก้บนใบเสร็จ</span><span className="block text-xs text-slate-500">หากยังไม่มีรูป จะแสดงวงกลมแทน</span></span><input type="checkbox" checked={settings.receipt_show_logo ?? true} onChange={(event) => update({ receipt_show_logo: event.target.checked })} /></label><p className="mt-2 text-xs text-slate-500">PNG, JPG หรือ WEBP ไม่เกิน 5MB ระบบจะแปลงเป็นขาวดำแบบไล่เฉดสำหรับเครื่องพิมพ์ thermal อัตโนมัติ</p></div>
        <div className="rounded-xl border border-slate-200 bg-white p-4"><h2 className="font-medium mb-3">ส่วนที่แสดงบนบิล</h2><div className="space-y-3"><label className="flex items-center justify-between gap-3"><span><span className="block text-sm font-medium">ผู้รับเงิน</span><span className="block text-xs text-slate-500">ชื่อพนักงานที่ทำรายการ</span></span><input type="checkbox" checked={settings.receipt_show_cashier ?? true} onChange={(event) => update({ receipt_show_cashier: event.target.checked })} /></label><label className="flex items-center justify-between gap-3"><span><span className="block text-sm font-medium">ข้อมูลสมาชิก</span><span className="block text-xs text-slate-500">ชื่อสมาชิกและแต้มสะสม</span></span><input type="checkbox" checked={settings.receipt_show_member ?? true} onChange={(event) => update({ receipt_show_member: event.target.checked })} /></label></div></div>
        <div className="rounded-xl border border-slate-200 bg-white p-4"><label className="block text-sm font-medium mb-1">ข้อความท้ายบิล</label><textarea value={settings.receipt_footer_text ?? ""} maxLength={255} rows={3} onChange={(event) => update({ receipt_footer_text: event.target.value })} placeholder="เช่น ขอบคุณที่ใช้บริการ" className="w-full rounded border px-3 py-2 text-sm" /><p className="mt-1 text-xs text-slate-500">แสดงใต้ยอดชำระเงิน เช่น คำขอบคุณ หรือนโยบายเปลี่ยนสินค้า</p></div>
      </section>
      <section className="flex flex-col items-center rounded-xl border border-slate-200 bg-slate-100 p-5 print:border-0 print:bg-white print:p-0"><h2 className="mb-4 self-start font-medium print:hidden">ตัวอย่างก่อนพิมพ์</h2><Receipt sale={SAMPLE_SALE} shop={settings} /></section>
    </div>
  </main>;
}
