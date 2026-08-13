"use client";

import { Tag } from "lucide-react";
import { useEffect, useState } from "react";
import { api, DiscountType, Product, Promotion, PromotionType } from "@/lib/api";

type BundleRow = { product_id: number; quantity: number };

function statusLabel(promo: Promotion): { text: string; className: string } {
  if (!promo.is_active) return { text: "ปิดใช้งาน", className: "bg-gray-100 text-gray-600" };
  if (promo.is_active_now) return { text: "ใช้งานอยู่", className: "bg-green-100 text-green-700" };
  const now = new Date();
  if (promo.start_at && new Date(promo.start_at) > now) {
    return { text: "ยังไม่ถึงกำหนด", className: "bg-amber-100 text-amber-700" };
  }
  return { text: "หมดอายุ", className: "bg-red-100 text-red-600" };
}

export default function PromotionsPage() {
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [type, setType] = useState<PromotionType>("time_discount");
  const [name, setName] = useState("");
  const [startAt, setStartAt] = useState("");
  const [endAt, setEndAt] = useState("");

  const [discountProductId, setDiscountProductId] = useState<number | "">("");
  const [discountType, setDiscountType] = useState<DiscountType>("percent");
  const [discountValue, setDiscountValue] = useState("");

  const [bundlePrice, setBundlePrice] = useState("");
  const [bundleRows, setBundleRows] = useState<BundleRow[]>([{ product_id: 0, quantity: 1 }]);

  function reload() {
    api.listPromotions().then(setPromotions).catch((e) => setError(String(e)));
    api.listProducts().then(setProducts).catch((e) => setError(String(e)));
  }

  useEffect(() => {
    reload();
  }, []);

  function resetForm() {
    setName("");
    setStartAt("");
    setEndAt("");
    setDiscountProductId("");
    setDiscountType("percent");
    setDiscountValue("");
    setBundlePrice("");
    setBundleRows([{ product_id: 0, quantity: 1 }]);
  }

  function addBundleRow() {
    setBundleRows((rows) => [...rows, { product_id: 0, quantity: 1 }]);
  }

  function updateBundleRow(index: number, patch: Partial<BundleRow>) {
    setBundleRows((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function removeBundleRow(index: number) {
    setBundleRows((rows) => rows.filter((_, i) => i !== index));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    try {
      if (type === "time_discount") {
        if (!discountProductId) {
          setError("กรุณาเลือกสินค้า");
          return;
        }
        await api.createPromotion({
          name,
          type,
          discount_type: discountType,
          discount_value: Number(discountValue),
          start_at: startAt ? new Date(startAt).toISOString() : null,
          end_at: endAt ? new Date(endAt).toISOString() : null,
          items: [{ product_id: Number(discountProductId), quantity: 1 }],
        });
      } else {
        const items = bundleRows.filter((r) => r.product_id > 0);
        if (items.length < 2) {
          setError("ซื้อคู่กันต้องเลือกสินค้าอย่างน้อย 2 รายการ");
          return;
        }
        await api.createPromotion({
          name,
          type,
          bundle_price: Number(bundlePrice),
          start_at: startAt ? new Date(startAt).toISOString() : null,
          end_at: endAt ? new Date(endAt).toISOString() : null,
          items,
        });
      }
      resetForm();
      reload();
    } catch (err) {
      setError(String(err));
    }
  }

  async function handleToggle(id: number) {
    await api.togglePromotion(id);
    reload();
  }

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <Tag className="w-5 h-5 text-amber-500" />
        โปรโมชั่น
      </h1>
      {error && (
        <p className="text-red-600 mb-4 cursor-pointer" onClick={() => setError(null)}>
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} className="border rounded-lg p-4 mb-6 space-y-3">
        <div className="flex gap-4">
          <label className="flex items-center gap-1.5 text-sm">
            <input
              type="radio"
              checked={type === "time_discount"}
              onChange={() => setType("time_discount")}
              className="accent-amber-500"
            />
            ลดราคาชั่วคราว
          </label>
          <label className="flex items-center gap-1.5 text-sm">
            <input
              type="radio"
              checked={type === "bundle"}
              onChange={() => setType("bundle")}
              className="accent-amber-500"
            />
            ซื้อคู่กัน (bundle)
          </label>
        </div>

        <input
          type="text"
          required
          placeholder="ชื่อโปรโมชั่น"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border rounded px-2 py-1 w-full"
        />

        {type === "time_discount" ? (
          <div className="flex flex-wrap gap-2 items-end">
            <select
              required
              value={discountProductId}
              onChange={(e) => setDiscountProductId(Number(e.target.value))}
              className="border rounded px-2 py-1 flex-1 min-w-48"
            >
              <option value="">เลือกสินค้า</option>
              {products.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.sku} — {p.name} ({p.price.toLocaleString()})
                </option>
              ))}
            </select>
            <select
              value={discountType}
              onChange={(e) => setDiscountType(e.target.value as DiscountType)}
              className="border rounded px-2 py-1"
            >
              <option value="percent">ลด %</option>
              <option value="amount">ลดจำนวนเงิน</option>
            </select>
            <input
              type="number"
              required
              step="0.01"
              placeholder={discountType === "percent" ? "เช่น 20" : "เช่น 10"}
              value={discountValue}
              onChange={(e) => setDiscountValue(e.target.value)}
              className="border rounded px-2 py-1 w-28"
            />
          </div>
        ) : (
          <div className="space-y-2">
            {bundleRows.map((row, i) => (
              <div key={i} className="flex gap-2 items-center">
                <select
                  value={row.product_id}
                  onChange={(e) => updateBundleRow(i, { product_id: Number(e.target.value) })}
                  className="border rounded px-2 py-1 flex-1"
                >
                  <option value={0}>เลือกสินค้า</option>
                  {products.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.sku} — {p.name} ({p.price.toLocaleString()})
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={1}
                  value={row.quantity}
                  onChange={(e) => updateBundleRow(i, { quantity: Number(e.target.value) })}
                  className="border rounded px-2 py-1 w-20"
                />
                {bundleRows.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeBundleRow(i)}
                    className="text-red-600 text-sm hover:underline"
                  >
                    ลบ
                  </button>
                )}
              </div>
            ))}
            <button
              type="button"
              onClick={addBundleRow}
              className="text-sm text-amber-600 hover:underline"
            >
              + เพิ่มสินค้าในเซ็ต
            </button>
            <input
              type="number"
              required
              step="0.01"
              placeholder="ราคาเซ็ตรวม"
              value={bundlePrice}
              onChange={(e) => setBundlePrice(e.target.value)}
              className="border rounded px-2 py-1 w-40"
            />
          </div>
        )}

        <div className="flex gap-2">
          <label className="flex flex-col text-xs text-gray-500">
            เริ่ม (ไม่บังคับ)
            <input
              type="datetime-local"
              value={startAt}
              onChange={(e) => setStartAt(e.target.value)}
              className="border rounded px-2 py-1"
            />
          </label>
          <label className="flex flex-col text-xs text-gray-500">
            สิ้นสุด (ไม่บังคับ)
            <input
              type="datetime-local"
              value={endAt}
              onChange={(e) => setEndAt(e.target.value)}
              className="border rounded px-2 py-1"
            />
          </label>
        </div>

        <button
          type="submit"
          className="px-4 py-2 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors"
        >
          สร้างโปรโมชั่น
        </button>
      </form>

      <table className="w-full text-sm border">
        <thead>
          <tr className="bg-gray-50 text-left">
            <th className="p-2">ชื่อ</th>
            <th className="p-2">ประเภท</th>
            <th className="p-2">รายละเอียด</th>
            <th className="p-2">สถานะ</th>
            <th className="p-2"></th>
          </tr>
        </thead>
        <tbody>
          {promotions.map((promo) => {
            const status = statusLabel(promo);
            return (
              <tr key={promo.id} className="border-t hover:bg-amber-50 transition-colors">
                <td className="p-2">{promo.name}</td>
                <td className="p-2">{promo.type === "time_discount" ? "ลดราคาชั่วคราว" : "ซื้อคู่กัน"}</td>
                <td className="p-2 text-gray-600">
                  {promo.type === "time_discount" ? (
                    <>
                      {promo.items[0]?.product_name}{" "}
                      {promo.discount_type === "percent"
                        ? `ลด ${promo.discount_value}%`
                        : `ลด ${promo.discount_value} บาท`}
                    </>
                  ) : (
                    <>
                      {promo.items.map((i) => `${i.product_name} x${i.quantity}`).join(" + ")} ={" "}
                      {promo.bundle_price?.toLocaleString()} บาท
                    </>
                  )}
                </td>
                <td className="p-2">
                  <span className={`px-2 py-0.5 rounded text-xs ${status.className}`}>{status.text}</span>
                </td>
                <td className="p-2">
                  <button onClick={() => handleToggle(promo.id)} className="text-blue-600 hover:underline">
                    {promo.is_active ? "ปิดใช้งาน" : "เปิดใช้งาน"}
                  </button>
                </td>
              </tr>
            );
          })}
          {promotions.length === 0 && !error && (
            <tr>
              <td colSpan={5} className="p-2 text-gray-500">
                ยังไม่มีโปรโมชั่น
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
