"use client";

import { ExternalLink, History, Printer, ReceiptText, Settings } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, ApiError, Sale } from "@/lib/api";

function money(value: number): string {
  return value.toLocaleString("th-TH", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function ReceiptsPage() {
  const [sales, setSales] = useState<Sale[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listSalesHistory({ status: "completed" }).then((items) => setSales(items.slice(0, 8))).catch((e) => {
      setError(e instanceof ApiError ? e.message : String(e));
    });
  }, []);

  return (
    <main className="p-4 md:p-6 lg:p-8 max-w-5xl w-full">
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="text-xl font-semibold flex items-center gap-2"><ReceiptText className="w-5 h-5 text-amber-500" />สร้าง/พิมพ์ใบเสร็จ</h1>
          <p className="text-sm text-slate-500 mt-1">สร้างใบเสร็จจากการชำระเงินในหน้าขาย แล้วพิมพ์ได้ทันทีหรือพิมพ์ซ้ำจากรายการล่าสุด</p>
        </div>
        <Link href="/pos" className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-medium text-white hover:bg-amber-600">
          <ReceiptText className="w-4 h-4" />สร้างใบเสร็จใหม่
        </Link>
      </div>

      {error && <p className="mb-4 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <section className="grid gap-4 md:grid-cols-2 mb-6">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <Printer className="w-5 h-5 text-amber-500 mb-2" />
          <h2 className="font-medium">พิมพ์ผ่านเครื่องพิมพ์ใบเสร็จ</h2>
          <p className="mt-1 text-sm text-slate-500">ตั้ง IP และพอร์ตของเครื่องพิมพ์ LAN (ปกติพอร์ต 9100) แล้วกด “พิมพ์ผ่านเครื่อง” ในใบเสร็จ</p>
          <Link href="/settings" className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-amber-700 hover:text-amber-800"><Settings className="w-4 h-4" />ตั้งค่าเครื่องพิมพ์</Link>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <ExternalLink className="w-5 h-5 text-sky-600 mb-2" />
          <h2 className="font-medium">พิมพ์ผ่าน USB / Windows</h2>
          <p className="mt-1 text-sm text-slate-500">เปิดใบเสร็จแล้วเลือก “เลือกเครื่องพิมพ์” เพื่อใช้เครื่องพิมพ์ที่ติดตั้งไว้ในอุปกรณ์นี้</p>
        </div>
      </section>

      <section className="rounded-xl border border-slate-200 bg-white overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <h2 className="font-medium flex items-center gap-2"><History className="w-4 h-4 text-slate-500" />ใบเสร็จล่าสุด</h2>
          <Link href="/sales/history" className="text-sm text-amber-700 hover:text-amber-800">ดูประวัติทั้งหมด</Link>
        </div>
        {sales.length === 0 ? <p className="px-4 py-8 text-center text-sm text-slate-400">ยังไม่มีใบเสร็จที่ชำระเงินสำเร็จ</p> : (
          <div className="divide-y divide-slate-100">
            {sales.map((sale) => <Link key={sale.id} href={`/sales/history?sale=${sale.id}`} className="flex items-center justify-between gap-4 px-4 py-3 hover:bg-amber-50">
              <div><div className="text-sm font-medium">ใบเสร็จ #{sale.receipt_no ?? sale.id}</div><div className="text-xs text-slate-500">{sale.completed_at ? new Date(sale.completed_at).toLocaleString("th-TH") : "-"}</div></div>
              <div className="text-sm font-semibold">฿{money(sale.total)}</div>
            </Link>)}
          </div>
        )}
      </section>
    </main>
  );
}
