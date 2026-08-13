"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/lib/auth";
import LockScreen from "./LockScreen";
import Sidebar from "./Sidebar";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading, locked } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isLoginPage = pathname === "/login";

  useEffect(() => {
    if (loading) return;
    if (!user && !isLoginPage) {
      router.replace("/login");
    } else if (user && isLoginPage) {
      router.replace("/pos");
    }
  }, [loading, user, isLoginPage, router]);

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-400 text-sm">กำลังโหลด...</div>;
  }

  if (isLoginPage) {
    return <>{children}</>;
  }

  if (!user) {
    return <div className="min-h-screen flex items-center justify-center text-slate-400 text-sm">กำลังนำไปหน้าเข้าสู่ระบบ...</div>;
  }

  if (locked) {
    return <LockScreen />;
  }

  return (
    <div className="min-h-screen flex w-full">
      <Sidebar />
      <div className="mobile-content flex-1 min-w-0">{children}</div>
    </div>
  );
}
