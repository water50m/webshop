"use client";

import { usePathname, useRouter } from "next/navigation";
import { Menu } from "lucide-react";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import LockScreen from "./LockScreen";
import { MobileNavContext } from "./MobileNavContext";
import Sidebar from "./Sidebar";

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { user, loading, locked } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isLoginPage = pathname === "/login";
  const isOnboardingPage = pathname === "/onboarding";
  const isPublicLegalPage = ["/privacy", "/terms", "/data-deletion"].includes(pathname);
  const isInboxPage = pathname === "/inbox";
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [desktopSidebarOpen, setDesktopSidebarOpen] = useState(false);

  useEffect(() => {
    if (loading) return;
    if (!user && !isLoginPage && !isOnboardingPage && !isPublicLegalPage) {
      router.replace("/login");
    } else if (user && isLoginPage) {
      router.replace("/pos");
    }
  }, [loading, user, isLoginPage, isOnboardingPage, isPublicLegalPage, router]);

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-slate-400 text-sm">กำลังโหลด...</div>;
  }

  if (isLoginPage || isOnboardingPage || isPublicLegalPage) {
    return <>{children}</>;
  }

  if (!user) {
    return <div className="min-h-screen flex items-center justify-center text-slate-400 text-sm">กำลังนำไปหน้าเข้าสู่ระบบ...</div>;
  }

  if (locked) {
    return <LockScreen />;
  }

  return (
    <div className="flex min-h-screen w-full flex-col sm:flex-row">
      {!isInboxPage && <header className="mobile-app-bar sm:hidden">
        <button onClick={() => setMobileNavOpen(true)} className="mobile-app-bar__menu" aria-label="เปิดเมนู" aria-expanded={mobileNavOpen}>
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-sm font-semibold text-slate-800">SStore</span>
      </header>}
      <Sidebar mobileOpen={mobileNavOpen} onMobileOpenChange={setMobileNavOpen} desktopOpen={desktopSidebarOpen} onDesktopOpenChange={setDesktopSidebarOpen} />
      <MobileNavContext.Provider value={setMobileNavOpen}>
        <div className={`mobile-content min-h-0 min-w-0 flex-1 transition-[margin] duration-200 ease-out ${desktopSidebarOpen ? "sm:ml-56" : ""}`}>{children}</div>
      </MobileNavContext.Provider>
    </div>
  );
}
