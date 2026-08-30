"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { MessageCircle, Store } from "lucide-react";
import { useAuth } from "@/lib/auth";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login, loginWithFacebook: loginWithNativeFacebook } = useAuth();
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login(username, password);
      router.replace("/pos");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "เข้าสู่ระบบไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  }

  async function loginWithFacebook() {
    setError(null);
    setSubmitting(true);
    try {
      const nativeAttempt = await loginWithNativeFacebook();
      if (nativeAttempt) {
        router.replace(`/onboarding?facebook_login=${encodeURIComponent(nativeAttempt)}`);
        return;
      }
      const { api } = await import("@/lib/api");
      window.location.assign((await api.startFacebookLogin()).authorization_url);
    } catch (err) {
      setSubmitting(false);
      setError(err instanceof ApiError ? err.message : "ไม่สามารถเริ่ม Facebook Login ได้");
    }
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center bg-slate-100">
      <div className="bg-white rounded-xl shadow-sm border border-slate-200 p-8 w-full max-w-sm">
        <div className="flex flex-col items-center gap-2 mb-6">
          <div className="w-12 h-12 rounded-full bg-amber-500 flex items-center justify-center">
            <Store className="w-6 h-6 text-white" />
          </div>
          <h1 className="text-lg font-semibold text-slate-800">SStore</h1>
          <p className="text-sm text-slate-500">เริ่มต้นใช้งานร้านของคุณ</p>
        </div>

        {error && (
          <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <button type="button" onClick={() => void loginWithFacebook()} disabled={submitting} className="w-full rounded-lg bg-[#1877f2] hover:bg-[#166fe5] disabled:opacity-60 text-white font-medium py-2.5 text-sm transition-colors inline-flex items-center justify-center gap-2"><MessageCircle className="h-4 w-4" />ดำเนินการต่อด้วย Facebook</button>
        <p className="mt-3 text-center text-xs leading-5 text-slate-500">สำหรับเจ้าของหรือผู้ดูแล Facebook Page ระบบจะแสดงเฉพาะ Page ที่คุณมีสิทธิ์ดูแล</p>

        <details className="mt-6 border-t border-slate-200 pt-4">
          <summary className="cursor-pointer text-center text-sm font-medium text-slate-600">เข้าสู่ระบบพนักงาน / ใช้บัญชี SStore</summary>
          <form onSubmit={handleSubmit} className="mt-4">
        <label className="block text-sm font-medium text-slate-700 mb-1">ชื่อผู้ใช้</label>
        <input
          autoFocus
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full mb-4 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
        />

        <label className="block text-sm font-medium text-slate-700 mb-1">รหัสผ่าน</label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full mb-6 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
        />

        <button
          type="submit"
          disabled={submitting}
          className="w-full rounded-lg bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white font-medium py-2.5 text-sm transition-colors"
        >
          {submitting ? "กำลังเข้าสู่ระบบ..." : "เข้าสู่ระบบ"}
        </button>
          </form>
        </details>
      </div>
    </div>
  );
}
