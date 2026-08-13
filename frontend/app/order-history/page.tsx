"use client";

import { ChevronDown, ChevronUp, ClipboardList, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, ChatOrderHistoryCustomer } from "@/lib/api";

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("th-TH", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export default function ChatOrderHistoryPage() {
  const [customers, setCustomers] = useState<ChatOrderHistoryCustomer[]>([]);
  const [search, setSearch] = useState("");
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.listChatOrderHistory().then(setCustomers).catch((err) => setError(String(err)));
  }, []);

  const filteredCustomers = useMemo(() => {
    const keyword = search.trim().toLocaleLowerCase();
    if (!keyword) return customers;
    return customers.filter((customer) => customer.customer_display_name.toLocaleLowerCase().includes(keyword));
  }, [customers, search]);

  const totalOrders = customers.reduce((sum, customer) => sum + customer.order_count, 0);

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold"><ClipboardList className="h-5 w-5 text-amber-500" /> ประวัติออเดอร์แชต</h1>
          <p className="mt-1 text-sm text-slate-600">เก็บเฉพาะออเดอร์ที่ยืนยันแล้ว แม้ข้อความใน Inbox จะถูกล้าง</p>
        </div>
        <div className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900">ยืนยันแล้วทั้งหมด {totalOrders} ครั้ง</div>
      </div>

      <label className="relative mt-5 block max-w-md">
        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="ค้นหาชื่อลูกค้า" className="w-full rounded-lg border border-slate-300 py-2 pl-9 pr-3 outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-100" />
      </label>

      {error && <p className="mt-4 text-red-600">{error}</p>}
      <div className="mt-5 space-y-3">
        {filteredCustomers.map((customer) => {
          const isExpanded = expanded[customer.customer_id] ?? false;
          return (
            <section key={customer.customer_id} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <button onClick={() => setExpanded((current) => ({ ...current, [customer.customer_id]: !isExpanded }))} className="flex w-full items-center gap-3 p-4 text-left hover:bg-slate-50">
                <div className="min-w-0 flex-1">
                  <div className="truncate font-semibold text-slate-900">{customer.customer_display_name}</div>
                  <div className="mt-1 text-xs text-slate-500">สั่งล่าสุด {formatDateTime(customer.last_order_at)}</div>
                </div>
                <div className="hidden text-right text-sm sm:block"><div className="font-medium text-slate-800">{customer.order_count} ครั้ง</div><div className="text-xs text-slate-500">{customer.total_spent.toLocaleString(undefined, { minimumFractionDigits: 2 })} บาท</div></div>
                <div className="rounded-full bg-amber-100 px-2 py-1 text-xs font-medium text-amber-900 sm:hidden">{customer.order_count} ครั้ง</div>
                {isExpanded ? <ChevronUp className="h-5 w-5 shrink-0 text-slate-400" /> : <ChevronDown className="h-5 w-5 shrink-0 text-slate-400" />}
              </button>
              {isExpanded && <div className="border-t border-slate-200 bg-slate-50 p-3 space-y-2">
                {customer.orders.map((order) => <article key={order.id} className="rounded-lg border border-slate-200 bg-white p-3">
                  <div className="flex flex-wrap justify-between gap-2"><span className="text-sm font-medium">ออเดอร์ #{order.id}</span><span className="text-sm font-semibold text-emerald-700">{order.total.toLocaleString(undefined, { minimumFractionDigits: 2 })} บาท</span></div>
                  <div className="mt-1 text-xs text-slate-500">ยืนยันเมื่อ {formatDateTime(order.confirmed_at)}</div>
                  <ul className="mt-2 text-sm text-slate-700">{order.items.map((item, index) => <li key={`${item.product_name}-${index}`}>• {item.product_name} × {item.quantity} <span className="text-slate-400">({item.unit_price.toLocaleString()} บาท/ชิ้น)</span></li>)}</ul>
                </article>)}
              </div>}
            </section>
          );
        })}
        {filteredCustomers.length === 0 && !error && <p className="rounded-lg border border-dashed border-slate-300 p-6 text-center text-slate-500">ยังไม่มีออเดอร์แชตที่ยืนยันแล้ว</p>}
      </div>
    </main>
  );
}
