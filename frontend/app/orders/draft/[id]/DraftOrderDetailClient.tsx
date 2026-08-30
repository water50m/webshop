"use client";

import { Printer } from "lucide-react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api, DraftOrder, ShopSettings } from "@/lib/api";

export default function DraftOrderDetailClient() {
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();
  const router = useRouter();
  const id = Number(searchParams.get("id") ?? params.id);

  const [draftOrder, setDraftOrder] = useState<DraftOrder | null>(null);
  const [shop, setShop] = useState<ShopSettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getDraftOrder(id).then(setDraftOrder).catch((e) => setError(String(e)));
  }, [id]);

  useEffect(() => {
    api.getSettings().then(setShop).catch(() => setShop(null));
  }, []);

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
    <>
      <main className="print:hidden p-4 md:p-6 lg:p-8">
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

        <button onClick={() => window.print()} className="mb-3 px-4 py-2 rounded border border-slate-300 bg-white hover:bg-slate-50 transition-colors inline-flex items-center gap-2">
          <Printer className="w-4 h-4" />พิมพ์สรุปออเดอร์
        </button>

        {draftOrder.status === "pending" && (
          <div className="flex gap-2">
            <button onClick={handleConfirm} className="px-4 py-2 rounded bg-green-600 text-white hover:bg-green-700 transition-colors">ยืนยันออเดอร์</button>
            <button onClick={handleReject} className="px-4 py-2 rounded bg-gray-200 hover:bg-gray-300 transition-colors">ปฏิเสธ</button>
          </div>
        )}
      </main>
      <section className="order-summary-document hidden bg-white p-6 w-80 text-sm">
        {shop?.shop_name && <div className="text-center mb-2"><div className="font-semibold">{shop.shop_name}</div>{shop.address && <div className="text-xs text-gray-500 whitespace-pre-line">{shop.address}</div>}</div>}
        <h2 className="text-center font-semibold">สรุปออเดอร์</h2>
        <div className="border-y border-dashed py-1.5 my-3 text-xs text-gray-600 space-y-0.5">
          <div className="flex justify-between"><span>เลขที่ออเดอร์</span><span>#{draftOrder.id}</span></div>
          <div className="flex justify-between"><span>สถานะ</span><span>{draftOrder.status === "pending" ? "รอยืนยัน" : draftOrder.status === "confirmed" ? "ยืนยันแล้ว" : "ปฏิเสธ"}</span></div>
        </div>
        <table className="w-full mb-3"><thead className="border-b text-left text-xs text-gray-500"><tr><th className="pb-1">รายการ</th><th className="pb-1 text-right">จำนวนเงิน</th></tr></thead><tbody>{draftOrder.items.map((item) => <tr key={item.id}><td className="py-1">{item.product_name ?? item.matched_text} x{item.quantity}{item.special_request && <div className="text-xs text-gray-500">{item.special_request}</div>}</td><td className="py-1 text-right">{(item.unit_price * item.quantity).toLocaleString("th-TH", { minimumFractionDigits: 2 })}</td></tr>)}</tbody></table>
        <div className="border-t pt-2 flex justify-between font-semibold"><span>ยอดรวม</span><span>{draftOrder.total.toLocaleString("th-TH", { minimumFractionDigits: 2 })}</span></div>
        <p className="mt-3 text-center text-xs text-gray-500">เอกสารนี้เป็นสรุปออเดอร์ ยังไม่ใช่ใบเสร็จรับเงิน</p>
      </section>
    </>
  );
}
