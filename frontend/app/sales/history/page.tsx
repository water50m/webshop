"use client";

import { FileDown, History, Printer } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, Sale } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { downloadReceiptPdf } from "@/lib/receiptPdf";
import Receipt from "../../components/Receipt";

function money(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

const STATUS_LABEL: Record<string, string> = {
  held: "พักบิล",
  completed: "สำเร็จ",
  voided: "ยกเลิก/คืนเงิน",
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function SalesHistoryPage() {
  const { user } = useAuth();
  const canRefund = user?.role === "owner" || user?.role === "manager";
  const [start, setStart] = useState(today());
  const [end, setEnd] = useState(today());
  const [status, setStatus] = useState("completed");
  const [sales, setSales] = useState<Sale[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Sale | null>(null);
  const [refundQty, setRefundQty] = useState<Record<number, string>>({});
  const receiptRef = useRef<HTMLDivElement>(null);
  const [printingThermal, setPrintingThermal] = useState(false);
  const [printError, setPrintError] = useState<string | null>(null);

  async function handleDownloadPdf() {
    if (!receiptRef.current || !selected) return;
    await downloadReceiptPdf(receiptRef.current, `receipt-${selected.receipt_no ?? selected.id}.pdf`);
  }

  async function handlePrintThermal() {
    if (!selected) return;
    setPrintingThermal(true);
    setPrintError(null);
    try {
      await api.printReceiptThermal(selected.id);
    } catch (e) {
      setPrintError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setPrintingThermal(false);
    }
  }

  function handleBrowserPrint() {
    window.print();
  }

  function showError(e: unknown) {
    setError(e instanceof ApiError ? e.message : String(e));
  }

  async function reload() {
    try {
      const endExclusive = new Date(end);
      endExclusive.setDate(endExclusive.getDate() + 1);
      const list = await api.listSalesHistory({
        start: `${start}T00:00:00`,
        end: endExclusive.toISOString().slice(0, 19),
        status: status || undefined,
      });
      setSales(list);
    } catch (e) {
      showError(e);
    }
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void reload(), 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const saleId = Number(new URLSearchParams(window.location.search).get("sale"));
    if (saleId > 0) void openDetail(saleId);
    // The query parameter is intentionally read only when the page is opened.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function openDetail(id: number) {
    try {
      const sale = await api.getSale(id);
      setSelected(sale);
      setRefundQty({});
    } catch (e) {
      showError(e);
    }
  }

  async function submitRefund() {
    if (!selected) return;
    const items = Object.entries(refundQty)
      .map(([itemId, qty]) => ({ item_id: Number(itemId), quantity: Number(qty) }))
      .filter((i) => i.quantity > 0);
    if (items.length === 0) return;
    try {
      const updated = await api.refundSale(selected.id, items);
      setSelected(updated);
      setRefundQty({});
      reload();
    } catch (e) {
      showError(e);
    }
  }

  return (
    <div className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <History className="w-5 h-5 text-amber-500" />
        ประวัติบิล
      </h1>

      {error && (
        <p className="text-red-600 mb-2 cursor-pointer" onClick={() => setError(null)}>
          {error}
        </p>
      )}

      <div className="flex gap-2 mb-4 items-end">
        <div>
          <label className="block text-xs text-slate-500 mb-1">วันที่เริ่ม</label>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="border rounded px-2 py-1" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">ถึงวันที่</label>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className="border rounded px-2 py-1" />
        </div>
        <div>
          <label className="block text-xs text-slate-500 mb-1">สถานะ</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="border rounded px-2 py-1">
            <option value="">ทั้งหมด</option>
            <option value="completed">สำเร็จ</option>
            <option value="voided">ยกเลิก/คืนเงิน</option>
            <option value="held">พักบิล</option>
          </select>
        </div>
        <button onClick={reload} className="bg-amber-500 hover:bg-amber-600 text-white text-sm px-3 py-1.5 rounded-lg transition-colors">
          ค้นหา
        </button>
      </div>

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2.5 font-medium">เลขที่</th>
              <th className="px-4 py-2.5 font-medium">วันเวลา</th>
              <th className="px-4 py-2.5 font-medium">พนักงาน</th>
              <th className="px-4 py-2.5 font-medium">สถานะ</th>
              <th className="px-4 py-2.5 font-medium text-right">ยอดรวม</th>
            </tr>
          </thead>
          <tbody>
            {sales.map((sale) => (
              <tr key={sale.id} onClick={() => openDetail(sale.id)} className="border-t border-slate-100 hover:bg-amber-50 cursor-pointer">
                <td className="px-4 py-2.5">{sale.receipt_no ?? sale.id}</td>
                <td className="px-4 py-2.5 text-slate-500">
                  {sale.completed_at ? new Date(sale.completed_at).toLocaleString() : "-"}
                </td>
                <td className="px-4 py-2.5 text-slate-500">{sale.created_by_name ?? "-"}</td>
                <td className="px-4 py-2.5">{STATUS_LABEL[sale.status] ?? sale.status}</td>
                <td className="px-4 py-2.5 text-right font-medium">{money(sale.total)}</td>
              </tr>
            ))}
            {sales.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                  ไม่พบบิลในช่วงที่เลือก
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50 print:bg-white print:p-0">
          <div className="max-h-[90vh] overflow-y-auto">
            <Receipt ref={receiptRef} sale={selected} />
            {printError && <p className="text-red-600 text-xs mt-2 print:hidden">{printError}</p>}

            {selected.status === "completed" && !canRefund && (
              <div className="bg-amber-50 border border-amber-200 rounded p-3 mt-2 w-80 print:hidden text-sm text-amber-800">
                การคืนเงิน/คืนสินค้าต้องให้ผู้จัดการหรือเจ้าของร้านทำรายการ
              </div>
            )}

            {selected.status === "completed" && canRefund && (
              <div className="bg-white rounded p-4 mt-2 w-80 print:hidden">
                <h3 className="text-sm font-semibold mb-2">คืนสินค้า/คืนเงินบางรายการ</h3>
                {selected.items.map((item) => {
                  const remaining = item.quantity - item.refunded_quantity;
                  if (remaining <= 0) return null;
                  return (
                    <div key={item.id} className="flex items-center justify-between text-sm mb-1.5">
                      <span>
                        {item.product_name} (เหลือคืนได้ {remaining})
                      </span>
                      <input
                        type="number"
                        min={0}
                        max={remaining}
                        value={refundQty[item.id] ?? ""}
                        onChange={(e) => setRefundQty((r) => ({ ...r, [item.id]: e.target.value }))}
                        className="border rounded px-1.5 py-0.5 w-16 text-right"
                      />
                    </div>
                  );
                })}
                <button
                  onClick={submitRefund}
                  className="w-full mt-2 bg-red-600 hover:bg-red-700 text-white text-sm py-2 rounded-lg transition-colors"
                >
                  ยืนยันคืนเงิน
                </button>
              </div>
            )}

            <div className="flex gap-2 mt-2 print:hidden">
              <button
                onClick={handleDownloadPdf}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded border bg-white hover:bg-gray-50 transition-colors"
              >
                <FileDown className="w-4 h-4" />
                PDF
              </button>
              <button
                onClick={handleBrowserPrint}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded border bg-white hover:bg-gray-50 transition-colors"
              >
                <Printer className="w-4 h-4" />
                เลือกเครื่องพิมพ์
              </button>
              <button
                onClick={handlePrintThermal}
                disabled={printingThermal}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors disabled:opacity-50"
              >
                <Printer className="w-4 h-4" />
                {printingThermal ? "กำลังพิมพ์..." : "พิมพ์ผ่านเครื่อง"}
              </button>
              <button
                onClick={() => {
                  setSelected(null);
                  setPrintError(null);
                }}
                className="px-3 py-2 rounded border bg-white hover:bg-gray-50 transition-colors"
              >
                ปิด
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
