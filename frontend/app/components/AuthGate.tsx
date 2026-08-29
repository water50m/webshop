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
  const [desktopNavigation, setDesktopNavigation] = useState(false);

  useEffect(() => {
    // A desktop browser can report a narrow CSS viewport when it is zoomed in.
    // Fine pointer + hover keeps its persistent sidebar in that situation.
    const mediaQuery = window.matchMedia("(min-width: 40rem), (hover: hover) and (pointer: fine)");
    const updateNavigationMode = () => setDesktopNavigation(mediaQuery.matches);
    updateNavigationMode();
    mediaQuery.addEventListener("change", updateNavigationMode);
    return () => mediaQuery.removeEventListener("change", updateNavigationMode);
  }, []);

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
    <div className={`flex min-h-screen w-full ${desktopNavigation ? "flex-row" : "flex-col"}`}>
      {!isInboxPage && !desktopNavigation && <header className="mobile-app-bar">
        <button onClick={() => setMobileNavOpen(true)} className="mobile-app-bar__menu" aria-label="เปิดเมนู" aria-expanded={mobileNavOpen}>
          <Menu className="h-5 w-5" />
        </button>
        <span className="text-sm font-semibold text-slate-800">SStore</span>
      </header>}
      <Sidebar desktopNavigation={desktopNavigation} mobileOpen={mobileNavOpen} onMobileOpenChange={setMobileNavOpen} />
      <MobileNavContext.Provider value={setMobileNavOpen}>
        <div className="mobile-content min-h-0 min-w-0 flex-1">{children}</div>
      </MobileNavContext.Provider>
    </div>
  );
}
