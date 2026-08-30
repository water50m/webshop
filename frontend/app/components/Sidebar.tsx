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
  Radio,
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
  X,
  Beaker,
  ClipboardCheck,
  BrainCircuit,
  MessageCircle,
  Facebook,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth";
import { api, ApiError, Shop, UserRole } from "@/lib/api";

const COLLAPSE_STORAGE_KEY = "sidebar-collapsed";

const NAV_ITEMS: { href: string; label: string; icon: typeof Store; roles?: UserRole[]; facebookOnly?: boolean }[] = [
  { href: "/", label: "หน้าหลัก", icon: Home },
  { href: "/pos", label: "หน้าขาย (POS)", icon: LayoutDashboard },
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
  { href: "/print-bridge", label: "Print Bridge", icon: Radio, roles: ["owner", "manager"] },
  { href: "/users", label: "ผู้ใช้งาน", icon: Users, roles: ["owner"] },
  { href: "/facebook", label: "เชื่อม Facebook Page", icon: MessageCircle, roles: ["owner"] },
  { href: "/my-pages", label: "เพจ Facebook ของฉัน", icon: Facebook, facebookOnly: true },
  { href: "/page-team", label: "ทีมและสิทธิ์เพจ", icon: ShieldAlert },
];

const ROLE_LABEL: Record<UserRole, string> = {
  owner: "เจ้าของร้าน",
  manager: "ผู้จัดการ",
  cashier: "แคชเชียร์",
};

export default function Sidebar({ mobileOpen, onMobileOpenChange }: { mobileOpen: boolean; onMobileOpenChange: (open: boolean) => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, lock, refresh } = useAuth();
  const [showPinForm, setShowPinForm] = useState(false);
  const [pin, setPin] = useState("");
  const [pinError, setPinError] = useState<string | null>(null);
  const [savingPin, setSavingPin] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [shops, setShops] = useState<Shop[]>([]);
  const [activeShopId, setActiveShopId] = useState<string>("");

  useEffect(() => {
    const timer = window.setTimeout(() => {
      if (localStorage.getItem(COLLAPSE_STORAGE_KEY) === "1") setCollapsed(true);
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

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

  function changeShop(id: string) {
    setActiveShopId(id);
    window.localStorage.setItem("active-shop-id", id);
    window.location.reload();
  }

  function toggleCollapsed() {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(COLLAPSE_STORAGE_KEY, next ? "1" : "0");
      return next;
    });
  }

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

  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 print:hidden"
          onClick={() => onMobileOpenChange(false)}
        />
      )}
      {collapsed && (
        <div className="flex fixed inset-y-0 left-0 w-3 z-50 items-center group print:hidden">
          <button
            onClick={toggleCollapsed}
            title="แสดงเมนู"
            className="absolute left-0 top-1/2 -translate-y-1/2 bg-slate-900 text-white p-1.5 rounded-r-md shadow-md opacity-0 group-hover:opacity-100 transition-opacity"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      )}
      <aside
        className={`shrink-0 bg-slate-900 text-slate-200 min-h-screen flex flex-col print:hidden fixed sm:static inset-y-0 left-0 z-40 transform transition-all w-64 sm:w-56 ${mobileOpen ? "translate-x-0" : "-translate-x-full"} sm:translate-x-0 ${collapsed ? "sm:w-0 sm:overflow-hidden sm:border-r-0" : ""}`}
      >
        <div className="flex items-center justify-between gap-2 px-4 py-4 text-white border-b border-slate-700/60">
          <div className="min-w-0">
            <span className="flex items-center gap-2 font-semibold text-lg">
            <Store className="w-6 h-6 text-amber-400" />
            SStore
            </span>
            {activeShop?.facebook_page_name && <div className="mt-1 truncate pl-8 text-sm font-medium text-amber-300" title={activeShop.facebook_page_name}>{activeShop.facebook_page_name}</div>}
          </div>
          <button onClick={() => onMobileOpenChange(false)} className="min-h-11 min-w-11 -mr-2 text-slate-400 hover:text-white sm:hidden" aria-label="ปิดเมนู">
            <X className="w-5 h-5" />
          </button>
        </div>
        <button
          onClick={toggleCollapsed}
          title="ซ่อนเมนู"
          className="hidden sm:flex items-center justify-center gap-2 py-2 text-xs text-slate-400 hover:text-white hover:bg-slate-800 transition-colors border-b border-slate-700/60"
        >
          <ChevronLeft className="w-4 h-4" />
          ซ่อนเมนู
        </button>
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
          {shops.length > 0 && <select value={activeShopId} onChange={(event) => changeShop(event.target.value)} className="mb-3 h-8 w-full rounded bg-slate-800 px-2 text-xs text-white outline-none ring-1 ring-slate-700"><option value="" disabled>เลือกร้าน</option>{shops.map((shop) => <option key={shop.id} value={shop.id}>{shop.name}</option>)}</select>}
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
