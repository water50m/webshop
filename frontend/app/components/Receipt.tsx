"use client";

import { forwardRef, useEffect, useState } from "react";
import { api, Sale, ShopSettings } from "@/lib/api";

function money(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const METHOD_LABEL: Record<string, string> = {
  cash: "เงินสด",
  transfer: "โอน/พร้อมเพย์",
};

const Receipt = forwardRef<HTMLDivElement, { sale: Sale }>(function Receipt({ sale }, ref) {
  const [shop, setShop] = useState<ShopSettings | null>(null);

  useEffect(() => {
    api.getSettings().then(setShop).catch(() => setShop(null));
  }, []);

  return (
    <div ref={ref} className="bg-white rounded p-6 w-80 print:w-full print:shadow-none">
      {shop?.shop_name && (
        <div className="text-center mb-2">
          <div className="font-semibold">{shop.shop_name}</div>
          {shop.address && <div className="text-xs text-gray-500 whitespace-pre-line">{shop.address}</div>}
          {shop.tax_id && <div className="text-xs text-gray-500">เลขประจำตัวผู้เสียภาษี: {shop.tax_id}</div>}
        </div>
      )}
      <h2 className="text-center font-semibold mb-2">ใบเสร็จ</h2>
      <p className="text-center text-xs text-gray-500 mb-3">
        เลขที่ {sale.receipt_no ?? sale.id} &middot;{" "}
        {sale.completed_at ? new Date(sale.completed_at).toLocaleString() : new Date().toLocaleString()}
        {sale.created_by_name ? ` · ${sale.created_by_name}` : ""}
      </p>
      <table className="w-full text-sm mb-3">
        <tbody>
          {sale.items.map((item) => (
            <tr key={item.id}>
              <td className="py-0.5">
                {item.product_name} x{item.quantity}
                {item.modifiers.length > 0 && (
                  <div className="text-xs text-gray-500">+ {item.modifiers.map((m) => m.name).join(", ")}</div>
                )}
                {item.refunded_quantity > 0 && (
                  <span className="text-red-500 text-xs"> (คืน {item.refunded_quantity})</span>
                )}
              </td>
              <td className="py-0.5 text-right">{money(item.line_total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="border-t pt-2 text-sm space-y-1">
        <div className="flex justify-between">
          <span>ยอดรวม</span>
          <span>{money(sale.subtotal)}</span>
        </div>
        <div className="flex justify-between">
          <span>ส่วนลด</span>
          <span>{money(sale.total_discount)}</span>
        </div>
        <div className="flex justify-between font-semibold">
          <span>ยอดสุทธิ</span>
          <span>{money(sale.total)}</span>
        </div>
        {sale.payments.map((p, idx) => (
          <div key={idx} className="flex justify-between">
            <span>ชำระโดย{METHOD_LABEL[p.method] ?? p.method}</span>
            <span>{money(p.amount)}</span>
          </div>
        ))}
        {(sale.change_amount ?? 0) > 0 && (
          <div className="flex justify-between">
            <span>เงินทอน</span>
            <span>{money(sale.change_amount ?? 0)}</span>
          </div>
        )}
        {sale.customer_phone && (
          <div className="border-t pt-1 mt-1 text-xs text-gray-600">
            <div className="flex justify-between">
              <span>สมาชิก</span>
              <span>{sale.customer_name || sale.customer_phone}</span>
            </div>
            {sale.points_redeemed > 0 && (
              <div className="flex justify-between">
                <span>ใช้แต้มสะสม</span>
                <span>-{sale.points_redeemed}</span>
              </div>
            )}
            {sale.points_earned > 0 && (
              <div className="flex justify-between">
                <span>ได้รับแต้มสะสม</span>
                <span>+{sale.points_earned}</span>
              </div>
            )}
            {sale.customer_points_balance !== null && (
              <div className="flex justify-between">
                <span>แต้มสะสมคงเหลือ</span>
                <span>{sale.customer_points_balance}</span>
              </div>
            )}
          </div>
        )}
        {sale.status === "voided" && <div className="text-center text-red-600 font-medium pt-1">ยกเลิกบิลแล้ว</div>}
      </div>
    </div>
  );
});

export default Receipt;
