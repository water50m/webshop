"use client";

import { Beaker, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError, Ingredient } from "@/lib/api";

export default function IngredientsPage() {
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [error, setError] = useState<string | null>(null);

  const [name, setName] = useState("");
  const [unit, setUnit] = useState("");
  const [threshold, setThreshold] = useState("0");

  const [adjustChanges, setAdjustChanges] = useState<Record<number, string>>({});
  const [adjustNotes, setAdjustNotes] = useState<Record<number, string>>({});

  function reload() {
    api.listIngredients().then(setIngredients).catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }

  useEffect(() => {
    reload();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await api.createIngredient({ name: name.trim(), unit, low_stock_threshold: Number(threshold) || 0 });
      setName("");
      setUnit("");
      setThreshold("0");
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function handleAdjust(id: number) {
    const changeStr = adjustChanges[id];
    const change = Number(changeStr);
    if (!changeStr || Number.isNaN(change) || change === 0) return;
    try {
      await api.adjustIngredientStock(id, change, adjustNotes[id] || "");
      setAdjustChanges((prev) => ({ ...prev, [id]: "" }));
      setAdjustNotes((prev) => ({ ...prev, [id]: "" }));
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  async function handleDelete(id: number) {
    try {
      await api.deleteIngredient(id);
      reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err));
    }
  }

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <Beaker className="w-5 h-5 text-amber-500" />
        วัตถุดิบ
      </h1>
      <p className="text-sm text-gray-500 mb-4">
        ใช้ในระบบตัดสต๊อกแบบ &quot;ร้านนั่งทาน/ครัว&quot; — ตั้งสูตรสินค้าให้ใช้วัตถุดิบเหล่านี้ได้ที่หน้า &quot;สินค้า/สต๊อก&quot;
        (เปิดโหมดนี้ได้ที่หน้าตั้งค่า)
      </p>
      {error && (
        <p className="text-red-600 mb-4 cursor-pointer" onClick={() => setError(null)}>
          {error}
        </p>
      )}

      <form onSubmit={handleCreate} className="flex gap-2 mb-4">
        <input
          type="text"
          placeholder="ชื่อวัตถุดิบ เช่น เมล็ดกาแฟ"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border rounded px-2 py-1.5 flex-1"
        />
        <input
          type="text"
          placeholder="หน่วย เช่น กรัม, มล., ชิ้น"
          value={unit}
          onChange={(e) => setUnit(e.target.value)}
          className="border rounded px-2 py-1.5 w-32"
        />
        <input
          type="number"
          placeholder="เตือนเมื่อเหลือ"
          value={threshold}
          onChange={(e) => setThreshold(e.target.value)}
          className="border rounded px-2 py-1.5 w-28"
        />
        <button type="submit" className="px-3 py-1.5 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors">
          เพิ่ม
        </button>
      </form>

      <table className="w-full text-sm border">
        <thead>
          <tr className="bg-gray-50 text-left">
            <th className="p-2">ชื่อวัตถุดิบ</th>
            <th className="p-2">หน่วย</th>
            <th className="p-2">คงเหลือ</th>
            <th className="p-2">ปรับสต๊อก</th>
            <th className="p-2"></th>
          </tr>
        </thead>
        <tbody>
          {ingredients.map((i) => {
            const low = i.stock_quantity <= i.low_stock_threshold;
            return (
              <tr key={i.id} className={`border-t ${low ? "bg-red-50" : ""}`}>
                <td className="p-2">{i.name}</td>
                <td className="p-2 text-gray-500">{i.unit}</td>
                <td className={`p-2 ${low ? "text-red-600 font-semibold" : ""}`}>
                  {i.stock_quantity}
                  {low && " (ใกล้หมด)"}
                </td>
                <td className="p-2">
                  <div className="flex gap-1">
                    <input
                      type="number"
                      placeholder="+/-"
                      value={adjustChanges[i.id] ?? ""}
                      onChange={(e) => setAdjustChanges((prev) => ({ ...prev, [i.id]: e.target.value }))}
                      className="border rounded px-1 py-0.5 w-16"
                    />
                    <input
                      type="text"
                      placeholder="หมายเหตุ"
                      value={adjustNotes[i.id] ?? ""}
                      onChange={(e) => setAdjustNotes((prev) => ({ ...prev, [i.id]: e.target.value }))}
                      className="border rounded px-1 py-0.5 w-24"
                    />
                    <button onClick={() => handleAdjust(i.id)} className="px-2 py-0.5 rounded border">
                      ปรับ
                    </button>
                  </div>
                </td>
                <td className="p-2">
                  <button onClick={() => handleDelete(i.id)} className="text-red-500 hover:text-red-600">
                    <Trash2 className="w-4 h-4" />
                  </button>
                </td>
              </tr>
            );
          })}
          {ingredients.length === 0 && (
            <tr>
              <td colSpan={5} className="p-2 text-gray-500">
                ยังไม่มีวัตถุดิบ
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
