"use client";

import {
  LayoutDashboard,
  Inbox,
  ClipboardList,
  Package,
  Tag,
  Receipt,
  BarChart3,
  Settings,
  Store,
  Users,
  LogOut,
  History,
  Lock,
  KeyRound,
  Home,
  ShieldAlert,
  UserCircle,
  Truck,
  Beaker,
  ClipboardCheck,
  BrainCircuit,
  MessageCircle,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, ApiError, Shop, UserRole } from "@/lib/api";

const NAV_ITEMS: { href: string; label: string; icon: typeof Store; roles?: UserRole[]; facebookOnly?: boolean }[] = [
  { href: "/", label: "หน้าหลัก", icon: Home },
  { href: "/pos", label: "หน้าขาย (POS)", icon: LayoutDashboard },
  { href: "/receipts", label: "สร้าง/พิมพ์ใบเสร็จ", icon: Receipt },
  { href: "/sales/history", label: "ประวัติบิล", icon: History },
  { href: "/products", label: "สินค้า/สต๊อก", icon: Package },
  { href: "/ingredients", label: "วัตถุดิบ", icon: Beaker, roles: ["owner", "manager"] },
  { href: "/stocktake", label: "นับสต๊อก", icon: ClipboardCheck, roles: ["owner", "manager"] },
  { href: "/promotions", label: "โปรโมชั่น", icon: Tag, roles: ["owner", "manager"] },
  { href: "/inbox", label: "กล่องข้อความ", icon: Inbox },
  { href: "/order-history", label: "ประวัติออเดอร์แชต", icon: ClipboardList },
  { href: "/orders/draft", label: "ออเดอร์", icon: ClipboardList },
  { href: "/expenses", label: "รายจ่าย", icon: Receipt, roles: ["owner", "manager"] },
  { href: "/customers", label: "ลูกค้า/แต้มสะสม", icon: UserCircle },
  { href: "/suppliers", label: "ซัพพลายเออร์/PO", icon: Truck, roles: ["owner", "manager"] },
  { href: "/reports", label: "รายงาน", icon: BarChart3, roles: ["owner", "manager"] },
  { href: "/audit", label: "ประวัติยกเลิก/คืนเงิน", icon: ShieldAlert, roles: ["owner", "manager"] },
  { href: "/history-preparation", label: "เตรียมข้อมูลแชต", icon: BrainCircuit, roles: ["owner", "manager"] },
  { href: "/parser-v2", label: "ทดลอง Parser v2", icon: BrainCircuit, roles: ["owner", "manager"] },
  { href: "/settings", label: "ตั้งค่า", icon: Settings, roles: ["owner", "manager"] },
  { href: "/users", label: "ผู้ใช้งาน", icon: Users, roles: ["owner"] },
  { href: "/my-pages", label: "เพจ Facebook ของฉัน", icon: MessageCircle, facebookOnly: true },
  { href: "/page-team", label: "ทีมและสิทธิ์เพจ", icon: ShieldAlert },
];

const ROLE_LABEL: Record<UserRole, string> = {
  owner: "เจ้าของร้าน",
  manager: "ผู้จัดการ",
  cashier: "แคชเชียร์",
};

export default function Sidebar({ mobileOpen, onMobileOpenChange, desktopOpen, onDesktopOpenChange }: { mobileOpen: boolean; onMobileOpenChange: (open: boolean) => void; desktopOpen: boolean; onDesktopOpenChange: (open: boolean) => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, lock, refresh } = useAuth();
  const [showPinForm, setShowPinForm] = useState(false);
  const [pin, setPin] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);
  const [savingPin, setSavingPin] = useState(false);
  const [showDesktopReveal, setShowDesktopReveal] = useState(false);
  const [shops, setShops] = useState<Shop[]>([]);
  const [activeShopId, setActiveShopId] = useState<string>("");

  useEffect(() => {
    void api.listShops().then((items) => {
      setShops(items);
      const saved = window.localStorage.getItem("active-shop-id");
      const selected = items.find((item) => String(item.id) === saved) ?? items[0];
      if (selected) {
        setActiveShopId(String(selected.id));
        window.localStorage.setItem("active-shop-id", String(selected.id));
      }
    }).catch(() => undefined);
  }, []);

  async function handleLogout() {
    await logout();
    router.replace("/login");
  }

  async function savePin() {
    if (!/^\d+$/.test(pin)) {
      setPinError("PIN ต้องเป็นตัวเลขเท่านั้น");
      return;
    }
    if (pin.length < 4) {
      setPinError("PIN ต้องมีอย่างน้อย 4 หลัก");
      return;
    }
    setSavingPin(true);
    setPinError(null);
    try {
      await api.setPin(pin);
      await refresh();
      setShowPinForm(false);
      setPin("");
    } catch (err) {
      setPinError(err instanceof ApiError ? err.message : "บันทึก PIN ไม่สำเร็จ");
    } finally {
      setSavingPin(false);
    }
  }

  const visibleItems = NAV_ITEMS.filter((item) => (!item.roles || (user && item.roles.includes(user.role))) && (!item.facebookOnly || user?.has_facebook_identity));
  const activeShop = shops.find((shop) => String(shop.id) === activeShopId);
  function openDesktopSidebar() {
    onDesktopOpenChange(true);
    setShowDesktopReveal(false);
  }

  function closeDesktopSidebar() {
    onDesktopOpenChange(false);
  }

  function dismissSidebar() {
    closeDesktopSidebar();
    onMobileOpenChange(false);
  }

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 print:hidden"
          onClick={() => onMobileOpenChange(false)}
        />
      )}
      <div className="fixed inset-y-0 left-0 z-30 hidden w-16 print:hidden sm:block" onMouseEnter={() => setShowDesktopReveal(true)} onMouseLeave={() => setShowDesktopReveal(false)}>
        {showDesktopReveal && !desktopOpen && <button onClick={openDesktopSidebar} className="absolute left-2 top-1/2 inline-flex h-12 w-12 -translate-y-1/2 items-center justify-center rounded-full border border-slate-300 bg-white text-black shadow-lg transition hover:border-slate-500 hover:text-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-amber-400" title="เปิดเมนู" aria-label="เปิดเมนู"><ChevronRight className="h-8 w-8" strokeWidth={2.5} /></button>}
      </div>
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex min-h-screen w-56 transform flex-col bg-slate-900 text-slate-200 transition-transform duration-200 ease-out print:hidden ${mobileOpen || desktopOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className="flex items-center justify-between gap-2 px-4 py-4 text-white border-b border-slate-700/60">
          <div className="min-w-0 flex-1">
            <span className="flex items-center gap-2 font-semibold text-lg">
            <Store className="w-6 h-6 text-amber-400" />
            SStore
            </span>
            {activeShop?.facebook_page_name && <div className="mt-1 truncate pl-8 text-sm font-medium text-amber-300" title={activeShop.facebook_page_name}>{activeShop.facebook_page_name}</div>}
          </div>
          <button onClick={dismissSidebar} title="ซ่อนเมนู" className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-slate-800 text-white shadow-sm transition-colors hover:bg-slate-700" aria-label="ซ่อนเมนู">
            <ChevronLeft className="h-5 w-5" strokeWidth={2.5} />
          </button>
        </div>
        <nav className="flex-1 py-3 overflow-y-auto">
          {visibleItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname?.startsWith(href + "/");
            return (
              <Link
                key={href}
                href={href}
                onClick={() => onMobileOpenChange(false)}
                className={`flex items-center gap-3 px-4 py-2.5 mx-2 rounded-lg text-sm transition-colors ${
                  active ? "bg-amber-500 text-white font-medium" : "text-slate-300 hover:bg-slate-800 hover:text-white"
                }`}
              >
                <Icon className="w-4 h-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>
      {user && (
        <div className="border-t border-slate-700/60 px-4 py-3">
          <div className="text-sm font-medium text-white truncate">{user.display_name || user.username}</div>
          <div className="text-xs text-slate-400 mb-2">{ROLE_LABEL[user.role]}</div>

          {showPinForm ? (
            <div className="mb-2 space-y-1.5">
              <input
                type="password"
                inputMode="numeric"
                placeholder="ตั้ง PIN ใหม่ (4-6 หลัก)"
                value={pin}
                onChange={(e) => setPin(e.target.value.slice(0, 6))}
                className="w-full rounded-md bg-slate-800 border border-slate-700 px-2 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-amber-400"
              />
              {pinError && <div className="text-xs text-red-400">{pinError}</div>}
              <div className="flex gap-2">
                <button
                  onClick={savePin}
                  disabled={savingPin}
                  className="text-xs bg-amber-500 hover:bg-amber-600 disabled:opacity-50 text-white rounded px-2 py-1"
                >
                  บันทึก
                </button>
                <button
                  onClick={() => {
                    setShowPinForm(false);
                    setPin("");
                    setPinError(null);
                  }}
                  className="text-xs text-slate-400 hover:text-white px-2 py-1"
                >
                  ยกเลิก
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowPinForm(true)}
              className="flex items-center gap-2 text-xs text-slate-300 hover:text-white transition-colors mb-2"
            >
              <KeyRound className="w-3.5 h-3.5" />
              {user.has_pin ? "เปลี่ยน PIN" : "ตั้ง PIN ปลดล็อกด่วน"}
            </button>
          )}

          <div className="flex items-center gap-3">
            {user.has_pin && (
              <button onClick={lock} className="flex items-center gap-2 text-xs text-slate-300 hover:text-white transition-colors">
                <Lock className="w-3.5 h-3.5 shrink-0" />
                ล็อกหน้าจอ
              </button>
            )}
            <button
              onClick={handleLogout}
              className="flex items-center gap-2 text-xs text-slate-300 hover:text-white transition-colors"
            >
              <LogOut className="w-3.5 h-3.5 shrink-0" />
              ออกจากระบบ
            </button>
          </div>
        </div>
      )}
      </aside>
    </>
  );
}
