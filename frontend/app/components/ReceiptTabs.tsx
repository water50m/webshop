"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/receipts", label: "จัดการใบเสร็จ" },
  { href: "/receipts/design", label: "ออกแบบใบเสร็จ" },
];

export default function ReceiptTabs({ className = "" }: { className?: string }) {
  const pathname = usePathname();
  return <nav aria-label="เมนูใบเสร็จ" className={`mb-6 flex w-full border-b border-slate-200 print:hidden ${className}`}>
    {TABS.map((tab) => {
      const active = pathname === tab.href || (tab.href === "/receipts/design" && pathname === "/receipt-designer");
      return <Link key={tab.href} href={tab.href} className={`-mb-px border-b-2 px-4 py-3 text-sm transition-colors ${active ? "border-amber-500 font-semibold text-amber-700" : "border-transparent text-slate-500 hover:border-slate-300 hover:text-slate-800"}`}>{tab.label}</Link>;
    })}
  </nav>;
}
