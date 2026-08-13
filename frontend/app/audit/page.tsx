"use client";

import { ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError, SaleAuditLog } from "@/lib/api";

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

const ACTION_LABEL: Record<string, string> = {
  void: "ยกเลิกบิล",
  refund: "คืนเงิน/คืนสินค้า",
};

export default function AuditLogPage() {
  const [start, setStart] = useState(today());
  const [end, setEnd] = useState(today());
  const [logs, setLogs] = useState<SaleAuditLog[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function reload() {
    try {
      const endExclusive = new Date(end);
      endExclusive.setDate(endExclusive.getDate() + 1);
      const list = await api.listSaleAuditLogs({
        start: `${start}T00:00:00`,
        end: endExclusive.toISOString().slice(0, 19),
      });
      setLogs(list);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void reload(), 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <ShieldAlert className="w-5 h-5 text-amber-500" />
        ประวัติการยกเลิก/คืนเงิน
      </h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="flex gap-2 mb-4 items-end">
        <label className="flex flex-col text-sm">
          จากวันที่
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="border rounded px-2 py-1" />
        </label>
        <label className="flex flex-col text-sm">
          ถึงวันที่
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="border rounded px-2 py-1" />
        </label>
        <button onClick={reload} className="px-4 py-1.5 rounded border hover:bg-gray-50 transition-colors">
          ค้นหา
        </button>
      </div>

      <table className="w-full text-sm border">
        <thead>
          <tr className="bg-gray-50 text-left">
            <th className="p-2">วันที่/เวลา</th>
            <th className="p-2">บิลเลขที่</th>
            <th className="p-2">การกระทำ</th>
            <th className="p-2">ทำโดย</th>
            <th className="p-2">หมายเหตุ</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((log) => (
            <tr key={log.id} className="border-t">
              <td className="p-2 whitespace-nowrap">{new Date(log.created_at).toLocaleString()}</td>
              <td className="p-2">{log.receipt_no ?? log.sale_id}</td>
              <td className="p-2">
                <span
                  className={`px-2 py-0.5 rounded text-xs ${
                    log.action === "void" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-700"
                  }`}
                >
                  {ACTION_LABEL[log.action] ?? log.action}
                </span>
              </td>
              <td className="p-2">{log.user_name ?? "-"}</td>
              <td className="p-2 text-gray-500">{log.note || "-"}</td>
            </tr>
          ))}
          {logs.length === 0 && !error && (
            <tr>
              <td colSpan={5} className="p-2 text-gray-500">
                ไม่พบรายการในช่วงเวลานี้
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
