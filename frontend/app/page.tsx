"use client";

import { AlertTriangle, Clock, Receipt, Store, TrendingUp } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, Shift, TodaySummary } from "@/lib/api";
import { useAuth } from "@/lib/auth";

function money(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function Home() {
  const { user } = useAuth();
  const canSeeOverview = user?.role === "owner" || user?.role === "manager";
  const [summary, setSummary] = useState<TodaySummary | null>(null);
  const [myShift, setMyShift] = useState<Shift | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (canSeeOverview) {
      api.getTodaySummary().then(setSummary).catch((e) => setError(String(e)));
    }
    api.getCurrentShift().then(setMyShift).catch(() => setMyShift(null));
  }, [canSeeOverview]);

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <div className="flex items-center gap-2 mb-1">
        <Store className="w-6 h-6 text-amber-500" />
        <h1 className="text-2xl font-semibold text-slate-800">shop-sys back-office</h1>
      </div>
      <p className="text-slate-500 mb-6">
        สวัสดี {user?.display_name || user?.username} เลือกเมนูจากแถบด้านซ้าย หรือเริ่มขายได้ที่นี่
      </p>

      <Link
        href="/pos"
        className="inline-block mb-6 px-5 py-2.5 rounded-lg bg-amber-500 text-white font-medium hover:bg-amber-600 transition-colors"
      >
        เริ่มขาย (POS)
      </Link>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      {canSeeOverview && summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="border border-amber-200 bg-amber-50 rounded-lg p-3">
              <div className="text-xs text-gray-500 flex items-center gap-1">
                <TrendingUp className="w-3.5 h-3.5" />
                ยอดขายวันนี้
              </div>
              <div className="text-lg font-semibold text-amber-700">{money(summary.total_revenue)}</div>
            </div>
            <div className="border rounded-lg p-3">
              <div className="text-xs text-gray-500 flex items-center gap-1">
                <Receipt className="w-3.5 h-3.5" />
                จำนวนบิลวันนี้
              </div>
              <div className="text-lg font-semibold">{summary.sale_count}</div>
            </div>
            <div className={`border rounded-lg p-3 ${summary.low_stock_products.length > 0 ? "border-red-200 bg-red-50" : ""}`}>
              <div className="text-xs text-gray-500 flex items-center gap-1">
                <AlertTriangle className="w-3.5 h-3.5" />
                สินค้าใกล้หมด
              </div>
              <div className={`text-lg font-semibold ${summary.low_stock_products.length > 0 ? "text-red-600" : ""}`}>
                {summary.low_stock_products.length}
              </div>
            </div>
            <div className="border rounded-lg p-3">
              <div className="text-xs text-gray-500 flex items-center gap-1">
                <Clock className="w-3.5 h-3.5" />
                กะที่เปิดอยู่
              </div>
              <div className="text-lg font-semibold">{summary.open_shifts.length}</div>
            </div>
          </div>

          {summary.low_stock_products.length > 0 && (
            <div className="border rounded-lg p-3">
              <h2 className="text-sm font-medium mb-2">สินค้าใกล้หมด</h2>
              <ul className="text-sm space-y-1">
                {summary.low_stock_products.map((p) => (
                  <li key={p.id} className="flex justify-between text-gray-600">
                    <span>
                      {p.name} <span className="text-gray-400">({p.sku})</span>
                    </span>
                    <span className="text-red-600 font-medium">เหลือ {p.stock_quantity}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {summary.open_shifts.length > 0 && (
            <div className="border rounded-lg p-3">
              <h2 className="text-sm font-medium mb-2">กะที่เปิดอยู่ขณะนี้</h2>
              <ul className="text-sm space-y-1">
                {summary.open_shifts.map((s) => (
                  <li key={s.id} className="flex justify-between text-gray-600">
                    <span>{s.opened_by_name}</span>
                    <span className="text-gray-400">เปิดเมื่อ {new Date(s.opened_at).toLocaleTimeString()}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {!canSeeOverview && (
        <div className="border rounded-lg p-3 max-w-sm">
          <h2 className="text-sm font-medium mb-1">กะของฉัน</h2>
          {myShift ? (
            <p className="text-sm text-gray-600">
              เปิดกะตั้งแต่ {new Date(myShift.opened_at).toLocaleTimeString()} (เงินตั้งต้น {money(myShift.opening_cash)})
            </p>
          ) : (
            <p className="text-sm text-gray-500">ยังไม่ได้เปิดกะ — ไปที่หน้าขายเพื่อเปิดกะ</p>
          )}
        </div>
      )}
    </main>
  );
}
