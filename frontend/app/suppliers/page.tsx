"use client";

import { Plus, Trash2, Truck } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError, Product, PurchaseOrder, Supplier } from "@/lib/api";

type ItemRow = { product_id: number | ""; quantity: string; unit_cost: string };

const STATUS_LABEL: Record<string, { text: string; className: string }> = {
  draft: { text: "ฉบับร่าง", className: "bg-gray-100 text-gray-600" },
  ordered: { text: "สั่งซื้อแล้ว", className: "bg-amber-100 text-amber-700" },
  received: { text: "รับสินค้าแล้ว", className: "bg-green-100 text-green-700" },
  cancelled: { text: "ยกเลิก", className: "bg-red-100 text-red-600" },
};

function money(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function SuppliersPage() {
  const [suppliers, setSuppliers] = useState<Supplier[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [orders, setOrders] = useState<PurchaseOrder[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [supplierName, setSupplierName] = useState("");
  const [supplierPhone, setSupplierPhone] = useState("");

  const [poSupplierId, setPoSupplierId] = useState<number | "">("");
  const [poNote, setPoNote] = useState("");
  const [rows, setRows] = useState<ItemRow[]>([{ product_id: "", quantity: "1", unit_cost: "" }]);

  function reload() {
    api.listSuppliers().then(setSuppliers).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
    api.listProducts().then(setProducts).catch(() => setProducts([]));
    api.listPurchaseOrders().then(setOrders).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }

  useEffect(() => {
    reload();
  }, []);

  async function handleCreateSupplier(e: React.FormEvent) {
    e.preventDefault();
    if (!supplierName.trim()) return;
    try {
      await api.createSupplier({ name: supplierName.trim(), phone: supplierPhone, address: "", note: "" });
      setSupplierName("");
      setSupplierPhone("");
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  function addRow() {
    setRows((r) => [...r, { product_id: "", quantity: "1", unit_cost: "" }]);
  }

  function updateRow(idx: number, patch: Partial<ItemRow>) {
    setRows((r) => r.map((row, i) => (i === idx ? { ...row, ...patch } : row)));
  }

  function removeRow(idx: number) {
    setRows((r) => r.filter((_, i) => i !== idx));
  }

  async function handleCreatePo(e: React.FormEvent) {
    e.preventDefault();
    if (!poSupplierId) return;
    const items = rows
      .filter((r) => r.product_id !== "" && Number(r.quantity) > 0)
      .map((r) => ({ product_id: Number(r.product_id), quantity: Number(r.quantity), unit_cost: Number(r.unit_cost) || 0 }));
    if (items.length === 0) return;
    try {
      await api.createPurchaseOrder({ supplier_id: Number(poSupplierId), note: poNote, items });
      setPoNote("");
      setRows([{ product_id: "", quantity: "1", unit_cost: "" }]);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function handleReceive(id: number) {
    try {
      await api.receivePurchaseOrder(id);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function handleCancel(id: number) {
    try {
      await api.cancelPurchaseOrder(id);
      reload();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <Truck className="w-5 h-5 text-amber-500" />
        ซัพพลายเออร์ / ใบสั่งซื้อ
      </h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-6">
      <section className="border rounded-lg p-4">
        <h2 className="text-sm font-medium mb-2">ซัพพลายเออร์</h2>
        <form onSubmit={handleCreateSupplier} className="flex gap-2 mb-3">
          <input
            type="text"
            placeholder="ชื่อซัพพลายเออร์"
            value={supplierName}
            onChange={(e) => setSupplierName(e.target.value)}
            className="border rounded px-2 py-1.5 flex-1"
          />
          <input
            type="text"
            placeholder="เบอร์โทร"
            value={supplierPhone}
            onChange={(e) => setSupplierPhone(e.target.value)}
            className="border rounded px-2 py-1.5 w-36"
          />
          <button type="submit" className="px-3 py-1.5 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors">
            เพิ่ม
          </button>
        </form>
        <ul className="text-sm space-y-1">
          {suppliers.map((s) => (
            <li key={s.id} className="flex justify-between border-t pt-1">
              <span>{s.name}</span>
              <span className="text-gray-500">{s.phone}</span>
            </li>
          ))}
          {suppliers.length === 0 && <li className="text-gray-500">ยังไม่มีซัพพลายเออร์</li>}
        </ul>
      </section>

      <section className="border rounded-lg p-4">
        <h2 className="text-sm font-medium mb-2">สร้างใบสั่งซื้อใหม่</h2>
        <form onSubmit={handleCreatePo} className="space-y-2">
          <select
            value={poSupplierId}
            onChange={(e) => setPoSupplierId(e.target.value ? Number(e.target.value) : "")}
            className="border rounded px-2 py-1.5 w-full"
          >
            <option value="">เลือกซัพพลายเออร์</option>
            {suppliers.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
          {rows.map((row, idx) => (
            <div key={idx} className="flex gap-2">
              <select
                value={row.product_id}
                onChange={(e) => updateRow(idx, { product_id: e.target.value ? Number(e.target.value) : "" })}
                className="border rounded px-2 py-1.5 flex-1"
              >
                <option value="">เลือกสินค้า</option>
                {products.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} ({p.sku})
                  </option>
                ))}
              </select>
              <input
                type="number"
                placeholder="จำนวน"
                value={row.quantity}
                onChange={(e) => updateRow(idx, { quantity: e.target.value })}
                className="border rounded px-2 py-1.5 w-24"
              />
              <input
                type="number"
                placeholder="ต้นทุน/หน่วย"
                value={row.unit_cost}
                onChange={(e) => updateRow(idx, { unit_cost: e.target.value })}
                className="border rounded px-2 py-1.5 w-28"
              />
              {rows.length > 1 && (
                <button type="button" onClick={() => removeRow(idx)} className="text-red-500 px-1">
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
          <button type="button" onClick={addRow} className="text-xs flex items-center gap-1 text-amber-600 hover:text-amber-700">
            <Plus className="w-3.5 h-3.5" />
            เพิ่มรายการสินค้า
          </button>
          <input
            type="text"
            placeholder="หมายเหตุ (ไม่บังคับ)"
            value={poNote}
            onChange={(e) => setPoNote(e.target.value)}
            className="border rounded px-2 py-1.5 w-full"
          />
          <button type="submit" className="px-3 py-1.5 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors">
            สร้างใบสั่งซื้อ
          </button>
        </form>
      </section>
      </div>

      <section>
        <h2 className="text-sm font-medium mb-2">รายการใบสั่งซื้อ</h2>
        <div className="columns-1 lg:columns-2 gap-3">
          {orders.map((po) => {
            const status = STATUS_LABEL[po.status] ?? { text: po.status, className: "bg-gray-100" };
            return (
              <div key={po.id} className="border rounded-lg p-3 mb-3 break-inside-avoid">
                <div className="flex justify-between items-center mb-1">
                  <span className="font-medium">
                    #{po.id} {po.supplier_name}
                  </span>
                  <span className={`text-xs px-2 py-0.5 rounded ${status.className}`}>{status.text}</span>
                </div>
                <ul className="text-sm text-gray-600 mb-2">
                  {po.items.map((i) => (
                    <li key={i.id}>
                      {i.product_name} x{i.quantity} @ {money(i.unit_cost)}
                    </li>
                  ))}
                </ul>
                <div className="flex justify-between items-center text-sm">
                  <span>รวม {money(po.total_cost)}</span>
                  {po.status === "draft" || po.status === "ordered" ? (
                    <span className="flex gap-2">
                      <button onClick={() => handleReceive(po.id)} className="text-green-700 hover:underline">
                        รับสินค้าเข้าสต๊อก
                      </button>
                      <button onClick={() => handleCancel(po.id)} className="text-red-600 hover:underline">
                        ยกเลิก
                      </button>
                    </span>
                  ) : null}
                </div>
              </div>
            );
          })}
          {orders.length === 0 && <p className="text-gray-500 text-sm">ยังไม่มีใบสั่งซื้อ</p>}
        </div>
      </section>
    </main>
  );
}
