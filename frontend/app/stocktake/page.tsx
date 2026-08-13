"use client";

import { ClipboardCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError, StocktakeSession } from "@/lib/api";

const STATUS_LABEL: Record<string, string> = { open: "กำลังนับ", closed: "ปิดแล้ว" };

function diffLabel(expected: number, counted: number | null): string {
  if (counted === null) return "ยังไม่นับ";
  const diff = counted - expected;
  if (diff === 0) return "ตรง";
  return diff > 0 ? `+${diff}` : `${diff}`;
}

export default function StocktakePage() {
  const [current, setCurrent] = useState<StocktakeSession | null>(null);
  const [history, setHistory] = useState<StocktakeSession[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [counts, setCounts] = useState<Record<number, string>>({});
  const [closing, setClosing] = useState(false);
  const [closeSummary, setCloseSummary] = useState<string | null>(null);

  function reload() {
    api
      .getCurrentStocktakeSession()
      .then((session) => {
        setCurrent(session);
        if (session) {
          const initial: Record<number, string> = {};
          for (const line of session.lines) {
            initial[line.id] = line.counted_quantity !== null ? String(line.counted_quantity) : "";
          }
          setCounts(initial);
        }
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    api.listStocktakeSessions().then(setHistory).catch(() => {});
  }

  useEffect(() => {
    reload();
  }, []);

  async function handleOpen() {
    try {
      await api.openStocktakeSession(note);
      setNote("");
      setCloseSummary(null);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function submitCount(lineId: number, value: string) {
    if (!current) return;
    const counted = value.trim() === "" ? null : Number(value);
    if (counted !== null && Number.isNaN(counted)) return;
    try {
      await api.submitStocktakeCount(current.id, lineId, counted);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function handleClose() {
    if (!current) return;
    setClosing(true);
    try {
      const result = await api.closeStocktakeSession(current.id);
      setCloseSummary(`ปรับสต๊อก ${result.adjusted_count} รายการ, ข้ามที่ยังไม่นับ ${result.skipped_count} รายการ`);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setClosing(false);
    }
  }

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <ClipboardCheck className="w-5 h-5 text-amber-500" />
        นับสต๊อก
      </h1>
      {error && (
        <p className="text-red-600 mb-4 cursor-pointer" onClick={() => setError(null)}>
          {error}
        </p>
      )}
      {closeSummary && <p className="text-green-700 mb-4">{closeSummary}</p>}

      {!current ? (
        <div className="border rounded-lg p-4 mb-6">
          <p className="text-sm text-gray-600 mb-2">
            เปิดรอบนับสต๊อกใหม่จะสร้างรายการให้นับตามระบบตัดสต๊อกที่ตั้งไว้ในหน้าตั้งค่า (สินค้า หรือ วัตถุดิบ) โดยใช้สต๊อกปัจจุบันเป็นค่าที่คาดไว้
          </p>
          <div className="flex gap-2">
            <input
              type="text"
              placeholder="หมายเหตุ (ไม่บังคับ)"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              className="border rounded px-2 py-1.5 flex-1"
            />
            <button onClick={handleOpen} className="px-4 py-1.5 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors">
              เปิดรอบนับสต๊อก
            </button>
          </div>
        </div>
      ) : (
        <div className="border rounded-lg p-4 mb-6">
          <div className="flex items-center justify-between mb-3">
            <div className="text-sm text-gray-500">
              เปิดโดย {current.opened_by_name} · {new Date(current.opened_at).toLocaleString()}
              {current.note && ` · ${current.note}`}
            </div>
            <button
              onClick={handleClose}
              disabled={closing}
              className="px-3 py-1.5 rounded bg-red-600 text-white hover:bg-red-700 transition-colors disabled:opacity-50"
            >
              {closing ? "กำลังปิด..." : "ปิดรอบนับสต๊อก"}
            </button>
          </div>
          <table className="w-full text-sm border">
            <thead>
              <tr className="bg-gray-50 text-left">
                <th className="p-2">{current.entity_type === "ingredient" ? "วัตถุดิบ" : "สินค้า"}</th>
                <th className="p-2">หน่วย</th>
                <th className="p-2">คาดว่ามี</th>
                <th className="p-2">นับได้จริง</th>
                <th className="p-2">ผลต่าง</th>
              </tr>
            </thead>
            <tbody>
              {current.lines.map((line) => (
                <tr key={line.id} className="border-t">
                  <td className="p-2">{line.name}</td>
                  <td className="p-2 text-gray-500">{line.unit}</td>
                  <td className="p-2">{line.expected_quantity}</td>
                  <td className="p-2">
                    <input
                      type="number"
                      value={counts[line.id] ?? ""}
                      onChange={(e) => setCounts((prev) => ({ ...prev, [line.id]: e.target.value }))}
                      onBlur={(e) => submitCount(line.id, e.target.value)}
                      className="border rounded px-1.5 py-0.5 w-24"
                    />
                  </td>
                  <td className="p-2">{diffLabel(line.expected_quantity, line.counted_quantity)}</td>
                </tr>
              ))}
              {current.lines.length === 0 && (
                <tr>
                  <td colSpan={5} className="p-2 text-gray-500">
                    ไม่มีรายการให้นับ
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <section>
        <h2 className="text-sm font-medium mb-2">ประวัติรอบนับสต๊อก</h2>
        <div className="space-y-1.5">
          {history.map((s) => (
            <div key={s.id} className="border rounded px-3 py-2 text-sm flex justify-between">
              <span>
                #{s.id} {s.entity_type === "ingredient" ? "วัตถุดิบ" : "สินค้า"} · เปิดโดย {s.opened_by_name} ·{" "}
                {new Date(s.opened_at).toLocaleString()}
              </span>
              <span className={s.status === "open" ? "text-amber-600" : "text-gray-500"}>{STATUS_LABEL[s.status]}</span>
            </div>
          ))}
          {history.length === 0 && <p className="text-gray-500 text-sm">ยังไม่มีรอบนับสต๊อก</p>}
        </div>
      </section>
    </main>
  );
}
