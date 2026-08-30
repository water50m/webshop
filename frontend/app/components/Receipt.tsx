"use client";

import { forwardRef, useEffect, useState } from "react";
import { api, resolveImageUrl, Sale, ShopSettings } from "@/lib/api";

function money(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const METHOD_LABEL: Record<string, string> = {
  cash: "เงินสด",
  transfer: "โอน/พร้อมเพย์",
};

const Receipt = forwardRef<HTMLDivElement, { sale: Sale; shop?: ShopSettings }>(function Receipt({ sale, shop: suppliedShop }, ref) {
  const [shop, setShop] = useState<ShopSettings | null>(null);

  useEffect(() => {
    if (!suppliedShop) api.getSettings().then(setShop).catch(() => setShop(null));
  }, [suppliedShop]);

  const receiptShop = suppliedShop ?? shop;
  const paperWidth = receiptShop?.receipt_paper_width ?? 80;

  return (
    <div ref={ref} className={`receipt-document receipt-document--${paperWidth} bg-white rounded p-6 w-80 print:w-full print:shadow-none`}>
      {receiptShop && (
        <div className="text-center mb-2">
          {receiptShop.receipt_show_logo !== false && receiptShop.receipt_logo_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={resolveImageUrl(receiptShop.receipt_logo_url) ?? undefined} alt="โลโก้ร้าน" className="receipt-logo mx-auto mb-2 max-h-16 max-w-32 object-contain" />
          )}
          {receiptShop.receipt_show_logo !== false && !receiptShop.receipt_logo_url && <div aria-label="ตำแหน่งโลโก้ร้าน" className="receipt-logo-placeholder mx-auto mb-2 h-10 w-10 rounded-full bg-slate-900" />}
          {receiptShop.shop_name && <div className="font-semibold">{receiptShop.shop_name}</div>}
          {receiptShop.address && <div className="text-xs text-gray-500 whitespace-pre-line">{receiptShop.address}</div>}
          {receiptShop.tax_id && <div className="text-xs text-gray-500">เลขประจำตัวผู้เสียภาษี: {receiptShop.tax_id}</div>}
        </div>
      )}
      <h2 className="text-center font-semibold mb-2">ใบเสร็จรับเงิน</h2>
      <div className="border-y border-dashed py-1.5 mb-3 text-xs text-gray-600 space-y-0.5">
        <div className="flex justify-between"><span>เลขที่ใบเสร็จ</span><span>{sale.receipt_no ?? sale.id}</span></div>
        <div className="flex justify-between"><span>วันเวลา</span><span>{sale.completed_at ? new Date(sale.completed_at).toLocaleString("th-TH") : new Date().toLocaleString("th-TH")}</span></div>
        {receiptShop?.receipt_show_cashier !== false && sale.created_by_name && <div className="flex justify-between"><span>ผู้รับเงิน</span><span>{sale.created_by_name}</span></div>}
      </div>
      <table className="w-full text-sm mb-3">
        <thead className="border-b text-left text-xs text-gray-500">
          <tr><th className="pb-1 font-medium">รายการ</th><th className="pb-1 text-right font-medium">จำนวนเงิน</th></tr>
        </thead>
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
        {receiptShop?.receipt_show_member !== false && sale.customer_phone && (
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
        {sale.note && <div className="border-t pt-1 mt-1 text-xs text-gray-600">หมายเหตุ: {sale.note}</div>}
        {sale.status === "voided" && <div className="text-center text-red-600 font-medium pt-1">ยกเลิกบิลแล้ว</div>}
      </div>
      {(receiptShop?.receipt_footer_text || "ขอบคุณที่ใช้บริการ") && <p className="mt-4 text-center text-xs text-gray-500">{receiptShop?.receipt_footer_text || "ขอบคุณที่ใช้บริการ"}</p>}
    </div>
  );
});

export default Receipt;
