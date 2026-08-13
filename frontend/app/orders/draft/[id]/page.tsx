"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, DraftOrder } from "@/lib/api";

export default function DraftOrderDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = Number(params.id);

  const [draftOrder, setDraftOrder] = useState<DraftOrder | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getDraftOrder(id).then(setDraftOrder).catch((e) => setError(String(e)));
  }, [id]);

  async function handleConfirm() {
    await api.confirmDraftOrder(id);
    router.push("/orders/draft");
  }

  async function handleReject() {
    await api.rejectDraftOrder(id);
    router.push("/orders/draft");
  }

  if (error) return <main className="p-6 text-red-600">{error}</main>;
  if (!draftOrder) return <main className="p-6">Loading...</main>;

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-1">Draft Order #{draftOrder.id}</h1>
      <p className="text-sm text-gray-500 mb-4">
        Conversation #{draftOrder.conversation_id} &middot; สถานะ: {draftOrder.status}
      </p>

      <table className="w-full text-sm border mb-4">
        <thead>
          <tr className="bg-gray-50 text-left">
            <th className="p-2">สินค้า</th>
            <th className="p-2">ข้อความที่จับคู่</th>
            <th className="p-2">หมายเหตุ/ท็อปปิ้ง</th>
            <th className="p-2">จำนวน</th>
            <th className="p-2">ราคา/หน่วย</th>
            <th className="p-2">รวม</th>
          </tr>
        </thead>
        <tbody>
          {draftOrder.items.map((item) => (
            <tr key={item.id} className="border-t">
              <td className="p-2">{item.product_name ?? "(ไม่พบสินค้า)"}</td>
              <td className="p-2 text-gray-500">{item.matched_text}</td>
              <td className="p-2 text-amber-600">{item.special_request || "-"}</td>
              <td className="p-2">{item.quantity}</td>
              <td className="p-2">{item.unit_price.toLocaleString()}</td>
              <td className="p-2">{(item.unit_price * item.quantity).toLocaleString()}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {draftOrder.status === "pending" && (
        <div className="flex gap-2">
          <button
            onClick={handleConfirm}
            className="px-4 py-2 rounded bg-green-600 text-white hover:bg-green-700 transition-colors"
          >
            ยืนยันออเดอร์
          </button>
          <button
            onClick={handleReject}
            className="px-4 py-2 rounded bg-gray-200 hover:bg-gray-300 transition-colors"
          >
            ปฏิเสธ
          </button>
        </div>
      )}
    </main>
  );
}
