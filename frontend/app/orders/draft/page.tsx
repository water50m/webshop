"use client";

import { ClipboardList } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api, DraftOrder } from "@/lib/api";

export default function DraftOrdersPage() {
  const [draftOrders, setDraftOrders] = useState<DraftOrder[]>([]);
  const [error, setError] = useState<string | null>(null);

  function reload() {
    api.listDraftOrders("pending").then(setDraftOrders).catch((e) => setError(String(e)));
  }

  useEffect(() => {
    reload();
  }, []);

  async function handleConfirm(id: number) {
    await api.confirmDraftOrder(id);
    reload();
  }

  async function handleReject(id: number) {
    await api.rejectDraftOrder(id);
    reload();
  }

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <ClipboardList className="w-5 h-5 text-amber-500" />
        Draft Orders รอตรวจสอบ
      </h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}
      <ul className="space-y-3">
        {draftOrders.map((d) => (
          <li key={d.id} className="border rounded-lg p-4 hover:border-amber-300 transition-colors">
            <div className="flex justify-between items-start">
              <div>
                <div className="font-medium">
                  <Link href={`/orders/draft/${d.id}`} className="hover:underline">
                    Draft #{d.id}
                  </Link>{" "}
                  (conversation #{d.conversation_id})
                </div>
                <ul className="mt-2 text-sm text-gray-700 list-disc pl-5">
                  {d.items.map((item) => (
                    <li key={item.id}>
                      {item.product_name ?? item.matched_text} x{item.quantity}
                      {item.special_request && (
                        <span className="text-amber-600"> ({item.special_request})</span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => handleConfirm(d.id)}
                  className="px-3 py-1 rounded bg-green-600 text-white text-sm hover:bg-green-700"
                >
                  ยืนยัน
                </button>
                <button
                  onClick={() => handleReject(d.id)}
                  className="px-3 py-1 rounded bg-gray-200 text-sm hover:bg-gray-300"
                >
                  ปฏิเสธ
                </button>
              </div>
            </div>
          </li>
        ))}
        {draftOrders.length === 0 && !error && (
          <p className="text-gray-500">ไม่มี draft order ที่รอตรวจสอบ</p>
        )}
      </ul>
    </main>
  );
}
