"use client";

import { Lock, Delete } from "lucide-react";
import { useState } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function LockScreen() {
  const { user, unlock, logout } = useAuth();
  const [username, setUsername] = useState(user?.username ?? "");
  const [pin, setPin] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function submit(value: string) {
    if (value.length < 4) return;
    setSubmitting(true);
    setError(null);
    try {
      await unlock(username, value);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "ปลดล็อกไม่สำเร็จ");
      setPin("");
    } finally {
      setSubmitting(false);
    }
  }

  function press(digit: string) {
    if (submitting) return;
    setPin((p) => (p + digit).slice(0, 6));
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-900">
      <div className="bg-white rounded-xl shadow-lg p-6 w-full max-w-xs">
        <div className="flex flex-col items-center gap-2 mb-4">
          <div className="w-12 h-12 rounded-full bg-amber-500 flex items-center justify-center">
            <Lock className="w-6 h-6 text-white" />
          </div>
          <p className="text-sm text-slate-500">หน้าจอถูกล็อก</p>
        </div>

        <label className="block text-xs text-slate-500 mb-1">ชื่อผู้ใช้</label>
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full mb-3 rounded-lg border border-slate-300 px-3 py-2 text-sm text-center focus:outline-none focus:ring-2 focus:ring-amber-400"
        />

        <div className="flex justify-center gap-2 mb-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <div
              key={i}
              className={`w-3 h-3 rounded-full border ${i < pin.length ? "bg-amber-500 border-amber-500" : "border-slate-300"}`}
            />
          ))}
        </div>

        {error && <div className="mb-3 text-xs text-red-600 text-center">{error}</div>}

        <div className="grid grid-cols-3 gap-2 mb-3">
          {["1", "2", "3", "4", "5", "6", "7", "8", "9"].map((d) => (
            <button
              key={d}
              onClick={() => press(d)}
              className="py-2.5 rounded-lg border text-lg hover:bg-amber-50 transition-colors"
            >
              {d}
            </button>
          ))}
          <button
            onClick={() => setPin("")}
            className="py-2.5 rounded-lg border text-xs text-slate-500 hover:bg-slate-50 transition-colors"
          >
            ล้าง
          </button>
          <button onClick={() => press("0")} className="py-2.5 rounded-lg border text-lg hover:bg-amber-50 transition-colors">
            0
          </button>
          <button
            onClick={() => setPin((p) => p.slice(0, -1))}
            className="py-2.5 rounded-lg border flex items-center justify-center hover:bg-slate-50 transition-colors"
          >
            <Delete className="w-4 h-4" />
          </button>
        </div>

        <button
          onClick={() => submit(pin)}
          disabled={pin.length < 4 || submitting}
          className="w-full rounded-lg bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white font-medium py-2.5 text-sm transition-colors mb-2"
        >
          {submitting ? "กำลังตรวจสอบ..." : "ปลดล็อก"}
        </button>
        <button onClick={logout} className="w-full text-xs text-slate-400 hover:text-slate-600">
          ออกจากระบบแทน
        </button>
      </div>
    </div>
  );
}
