"use client";

import { BarChart3, CalendarDays, Download, ReceiptText, TrendingDown, TrendingUp } from "lucide-react";
import { useEffect, useState } from "react";
import { api, DailyReport, ExpenseCategory, ProductPerformance, ReportSummary } from "@/lib/api";

const CATEGORY_LABELS: Record<ExpenseCategory, string> = {
  cost_of_goods: "ค่าสินค้า",
  shipping: "ค่าขนส่ง",
  rent: "ค่าเช่า",
  utilities: "ค่าน้ำ/ค่าไฟ",
  marketing: "ค่าโฆษณา",
  other: "อื่นๆ",
};

const SHOP_TYPE_LABELS = {
  individual: "บุคคลธรรมดา",
  juristic: "นิติบุคคล",
};

function formatMoney(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function shortDate(value: string): string {
  const [, month, day] = value.split("-");
  return `${day}/${month}`;
}

function DailyIncomeExpenseChart({ report }: { report: DailyReport }) {
  const maxValue = Math.max(1, ...report.days.flatMap((day) => [day.income, day.expense]));
  return (
    <section className="border rounded-lg p-4">
      <h2 className="font-medium mb-1">รายรับและรายจ่ายรายวัน</h2>
      <p className="text-xs text-gray-500 mb-4">รายรับรวมยอดขาย POS และออเดอร์ที่ยืนยันแล้ว</p>
      <div className="overflow-x-auto">
        <div className="min-w-[620px] h-64 flex items-end gap-2 border-b border-l px-3 pt-5">
          {report.days.map((day) => (
            <div key={day.date} className="h-full flex-1 min-w-8 flex flex-col justify-end items-center gap-1 group relative">
              <div className="absolute bottom-full mb-2 z-10 hidden group-hover:block whitespace-nowrap rounded bg-gray-900 px-2 py-1 text-xs text-white shadow">
                {shortDate(day.date)} · รายรับ {formatMoney(day.income)} · รายจ่าย {formatMoney(day.expense)}
              </div>
              <div className="w-full flex items-end justify-center gap-0.5 h-full">
                <div className="w-[42%] min-h-px rounded-t bg-amber-400" style={{ height: `${(day.income / maxValue) * 100}%` }} aria-label={`รายรับ ${day.date}: ${formatMoney(day.income)}`} />
                <div className="w-[42%] min-h-px rounded-t bg-rose-400" style={{ height: `${(day.expense / maxValue) * 100}%` }} aria-label={`รายจ่าย ${day.date}: ${formatMoney(day.expense)}`} />
              </div>
              <span className="text-[10px] text-gray-500 -mb-5 whitespace-nowrap">{shortDate(day.date)}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-7 flex gap-4 text-xs text-gray-600"><span><i className="inline-block w-2.5 h-2.5 rounded-sm bg-amber-400 mr-1" />รายรับ</span><span><i className="inline-block w-2.5 h-2.5 rounded-sm bg-rose-400 mr-1" />รายจ่าย</span></div>
    </section>
  );
}

export default function ReportsPage() {
  const now = new Date();
  const [year, setYear] = useState(now.getFullYear());
  const [month, setMonth] = useState<number | "">(now.getMonth() + 1);
  const [summary, setSummary] = useState<ReportSummary | null>(null);
  const [performance, setPerformance] = useState<ProductPerformance[]>([]);
  const [dailyReport, setDailyReport] = useState<DailyReport | null>(null);
  const [tab, setTab] = useState<"summary" | "daily">("summary");
  const [sortAsc, setSortAsc] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function periodBounds(): { start: string; end: string } {
    if (month === "") {
      return { start: `${year}-01-01T00:00:00`, end: `${year + 1}-01-01T00:00:00` };
    }
    const nextMonth = month === 12 ? 1 : month + 1;
    const nextYear = month === 12 ? year + 1 : year;
    return {
      start: `${year}-${String(month).padStart(2, "0")}-01T00:00:00`,
      end: `${nextYear}-${String(nextMonth).padStart(2, "0")}-01T00:00:00`,
    };
  }

  function reload() {
    api
      .getReportSummary(year, month === "" ? undefined : month)
      .then(setSummary)
      .catch((e) => setError(String(e)));
    const { start, end } = periodBounds();
    api
      .getProductPerformance(start, end)
      .then(setPerformance)
      .catch((e) => setError(String(e)));
    api
      .getDailyReport(start, end)
      .then(setDailyReport)
      .catch((e) => setError(String(e)));
  }

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year, month]);

  const sortedPerformance = [...performance].sort((a, b) =>
    sortAsc ? a.quantity_sold - b.quantity_sold : b.quantity_sold - a.quantity_sold
  );

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <BarChart3 className="w-5 h-5 text-amber-500" />
        สรุปกำไร-ขาดทุน
      </h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="flex gap-2 mb-6 items-end">
        <label className="flex flex-col text-sm">
          ปี
          <input
            type="number"
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="border rounded px-2 py-1 w-24"
          />
        </label>
        <label className="flex flex-col text-sm">
          เดือน
          <select
            value={month}
            onChange={(e) => setMonth(e.target.value === "" ? "" : Number(e.target.value))}
            className="border rounded px-2 py-1"
          >
            <option value="">ทั้งปี</option>
            {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="flex gap-2 mb-6 text-xs">
        <a
          href={api.exportProductsUrl()}
          className="flex items-center gap-1 px-2 py-1 rounded border hover:bg-gray-50 transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          Export สินค้า (CSV)
        </a>
        <a
          href={api.exportSalesUrl(periodBounds().start, periodBounds().end)}
          className="flex items-center gap-1 px-2 py-1 rounded border hover:bg-gray-50 transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          Export ยอดขาย (CSV)
        </a>
        <a
          href={api.exportExpensesUrl(periodBounds().start, periodBounds().end)}
          className="flex items-center gap-1 px-2 py-1 rounded border hover:bg-gray-50 transition-colors"
        >
          <Download className="w-3.5 h-3.5" />
          Export รายจ่าย (CSV)
        </a>
      </div>

      <div className="border-b mb-5 flex gap-1" role="tablist" aria-label="รูปแบบรายงาน">
        <button role="tab" aria-selected={tab === "summary"} onClick={() => setTab("summary")} className={`px-4 py-2 text-sm border-b-2 -mb-px transition-colors ${tab === "summary" ? "border-amber-500 text-amber-700 font-medium" : "border-transparent text-gray-500 hover:text-gray-800"}`}>
          ภาพรวม
        </button>
        <button role="tab" aria-selected={tab === "daily"} onClick={() => setTab("daily")} className={`px-4 py-2 text-sm border-b-2 -mb-px transition-colors ${tab === "daily" ? "border-amber-500 text-amber-700 font-medium" : "border-transparent text-gray-500 hover:text-gray-800"}`}>
          <CalendarDays className="inline w-4 h-4 mr-1 -mt-0.5" />สรุปรายวัน
        </button>
      </div>

      {tab === "summary" && summary && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 text-sm">
            <div className="border border-amber-200 bg-amber-50 rounded-lg p-3">
              <div className="text-gray-500">รายรับ</div>
              <div className="text-lg font-semibold text-amber-700">{formatMoney(summary.income)}</div>
            </div>
            <div className="border rounded-lg p-3">
              <div className="text-gray-500">ต้นทุนสินค้าที่ขาย (COGS)</div>
              <div className="text-lg font-semibold">{formatMoney(summary.cogs)}</div>
            </div>
            <div className="border border-sky-200 bg-sky-50 rounded-lg p-3">
              <div className="text-gray-500">กำไรขั้นต้น</div>
              <div className="text-lg font-semibold text-sky-700">{formatMoney(summary.gross_profit)}</div>
            </div>
            <div className="border rounded-lg p-3">
              <div className="text-gray-500">รายจ่ายรวม</div>
              <div className="text-lg font-semibold">{formatMoney(summary.total_expense)}</div>
            </div>
            <div className="border border-green-200 bg-green-50 rounded-lg p-3">
              <div className="text-gray-500">กำไรสุทธิ</div>
              <div className="text-lg font-semibold text-green-700">{formatMoney(summary.net_profit)}</div>
            </div>
            <div className="border rounded-lg p-3">
              <div className="text-gray-500">
                ภาษีประมาณการ ({SHOP_TYPE_LABELS[summary.shop_type]})
              </div>
              <div className="text-lg font-semibold">{formatMoney(summary.tax_estimate)}</div>
            </div>
          </div>
          <p className="text-xs text-gray-400">
            * ต้นทุนสินค้า/กำไรขั้นต้นคำนวณจากยอดขายหน้าร้าน (POS) ที่ตั้งต้นทุนต่อหน่วยไว้ในหน้าสินค้าเท่านั้น
          </p>

          <div className="columns-1 lg:columns-2 gap-4">
            <div className="mb-4 break-inside-avoid">
              <table className="w-full text-sm border">
                <thead>
                  <tr className="bg-gray-50 text-left">
                    <th className="p-2">หมวดรายจ่าย</th>
                    <th className="p-2">จำนวนเงิน</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(summary.expense_breakdown).map(([category, amount]) => (
                    <tr key={category} className="border-t">
                      <td className="p-2">{CATEGORY_LABELS[category as ExpenseCategory]}</td>
                      <td className="p-2">{formatMoney(amount)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-xs text-gray-500 mt-2">{summary.tax_disclaimer}</p>
            </div>

            <div className="mb-4 break-inside-avoid">
              <div className="flex items-center justify-between mb-2">
                <h2 className="text-sm font-medium flex items-center gap-1.5">
                  {sortAsc ? (
                    <TrendingDown className="w-4 h-4 text-red-500" />
                  ) : (
                    <TrendingUp className="w-4 h-4 text-green-600" />
                  )}
                  {sortAsc ? "สินค้าขายไม่ดี" : "สินค้าขายดี"}
                </h2>
                <button
                  onClick={() => setSortAsc((v) => !v)}
                  className="text-xs px-2 py-1 rounded border hover:bg-gray-50 transition-colors"
                >
                  {sortAsc ? "ดูขายดีที่สุด" : "ดูขายไม่ดีที่สุด"}
                </button>
              </div>
              <table className="w-full text-sm border">
                <thead>
                  <tr className="bg-gray-50 text-left">
                    <th className="p-2">สินค้า</th>
                    <th className="p-2">จำนวนที่ขายได้</th>
                    <th className="p-2">รายรับ</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedPerformance.map((row) => (
                    <tr key={`${row.product_id}-${row.sku}`} className="border-t">
                      <td className="p-2">
                        {row.name} <span className="text-gray-400">({row.sku})</span>
                      </td>
                      <td className="p-2">{row.quantity_sold}</td>
                      <td className="p-2">{formatMoney(row.revenue)}</td>
                    </tr>
                  ))}
                  {sortedPerformance.length === 0 && (
                    <tr>
                      <td colSpan={3} className="p-2 text-gray-500">
                        ยังไม่มีข้อมูลการขายในช่วงนี้
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {tab === "daily" && dailyReport && (
        <div className="space-y-5">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
            <div className="border border-amber-200 bg-amber-50 rounded-lg p-3"><div className="text-gray-500">รายรับในช่วงที่เลือก</div><div className="text-lg font-semibold text-amber-700">{formatMoney(dailyReport.days.reduce((total, day) => total + day.income, 0))}</div></div>
            <div className="border border-rose-200 bg-rose-50 rounded-lg p-3"><div className="text-gray-500">รายจ่ายในช่วงที่เลือก</div><div className="text-lg font-semibold text-rose-700">{formatMoney(dailyReport.days.reduce((total, day) => total + day.expense, 0))}</div></div>
            <div className="border rounded-lg p-3"><div className="text-gray-500">จำนวนออเดอร์</div><div className="text-lg font-semibold">{dailyReport.days.reduce((total, day) => total + day.order_count, 0).toLocaleString()}</div></div>
          </div>

          <DailyIncomeExpenseChart report={dailyReport} />

          <section className="border rounded-lg p-4 overflow-x-auto">
            <h2 className="font-medium mb-1">สินค้าขายดีตลอดกาล 5 อันดับแรก — ยอดขายในแต่ละวัน</h2>
            <p className="text-xs text-gray-500 mb-4">อันดับคำนวณจากจำนวนชิ้นที่ขายได้สะสมทั้งหมด โดยตัดสินค้าที่คืนแล้วออก</p>
            <table className="w-full min-w-[720px] text-sm">
              <thead><tr className="bg-gray-50 text-left"><th className="p-2">อันดับ / สินค้า</th><th className="p-2">ขายสะสม</th>{dailyReport.days.map((day) => <th key={day.date} className="p-2 text-center">{shortDate(day.date)}</th>)}</tr></thead>
              <tbody>{dailyReport.top_products.map((product, index) => (
                <tr key={`${product.sku}-${index}`} className="border-t"><td className="p-2"><span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-amber-100 text-amber-800 text-xs mr-2">{index + 1}</span>{product.name} <span className="text-gray-400">({product.sku})</span></td><td className="p-2">{product.quantity_sold}</td>{dailyReport.days.map((day) => <td key={day.date} className="p-2 text-center">{day.top_product_quantities[String(index)] ?? "—"}</td>)}</tr>
              ))}{dailyReport.top_products.length === 0 && <tr><td className="p-3 text-gray-500" colSpan={2 + dailyReport.days.length}>ยังไม่มีข้อมูลสินค้าที่ขายได้</td></tr>}</tbody>
            </table>
          </section>

          <section className="border rounded-lg p-4 overflow-x-auto">
            <h2 className="font-medium flex items-center gap-1.5 mb-3"><ReceiptText className="w-4 h-4 text-amber-500" />รายได้จากแต่ละออเดอร์</h2>
            <table className="w-full text-sm"><thead><tr className="bg-gray-50 text-left"><th className="p-2">วันที่ / เวลา</th><th className="p-2">ช่องทาง</th><th className="p-2">ออเดอร์</th><th className="p-2 text-right">รายได้สุทธิ</th></tr></thead><tbody>{dailyReport.orders.map((order) => <tr key={`${order.source}-${order.id}`} className="border-t"><td className="p-2">{new Date(order.completed_at).toLocaleString("th-TH")}</td><td className="p-2">{order.source === "pos" ? "POS" : "แชต"}</td><td className="p-2">{order.reference}</td><td className="p-2 text-right">{formatMoney(order.revenue)}</td></tr>)}{dailyReport.orders.length === 0 && <tr><td className="p-3 text-gray-500" colSpan={4}>ยังไม่มีออเดอร์ในช่วงที่เลือก</td></tr>}</tbody></table>
          </section>
        </div>
      )}
    </main>
  );
}
