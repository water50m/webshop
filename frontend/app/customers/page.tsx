"use client";

import { Users } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError, Customer } from "@/lib/api";

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);

  const [phone, setPhone] = useState("");
  const [name, setName] = useState("");

  const [editingId, setEditingId] = useState<number | null>(null);
  const [editPhone, setEditPhone] = useState("");
  const [editName, setEditName] = useState("");

  function reload(term?: string) {
    api
      .listCustomers(term || undefined)
      .then(setCustomers)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }

  useEffect(() => {
    reload();
  }, []);

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    reload(search);
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!phone.trim()) return;
    try {
      await api.createCustomer({ phone: phone.trim(), name });
      setPhone("");
      setName("");
      reload(search);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  function startEdit(c: Customer) {
    setEditingId(c.id);
    setEditPhone(c.phone);
    setEditName(c.name);
  }

  async function saveEdit() {
    if (editingId === null) return;
    try {
      await api.updateCustomer(editingId, { phone: editPhone.trim(), name: editName });
      setEditingId(null);
      reload(search);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  }

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <Users className="w-5 h-5 text-amber-500" />
        ลูกค้า/สมาชิกสะสมแต้ม
      </h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <form onSubmit={handleSearch} className="flex gap-2 mb-4">
        <input
          type="text"
          placeholder="ค้นหาเบอร์โทร/ชื่อ"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="border rounded px-2 py-1.5 flex-1"
        />
        <button type="submit" className="px-3 py-1.5 rounded border hover:bg-gray-50 transition-colors">
          ค้นหา
        </button>
      </form>

      <form onSubmit={handleCreate} className="flex gap-2 mb-6">
        <input
          type="text"
          placeholder="เบอร์โทร"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
          className="border rounded px-2 py-1.5 w-36"
        />
        <input
          type="text"
          placeholder="ชื่อลูกค้า (ไม่บังคับ)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="border rounded px-2 py-1.5 flex-1"
        />
        <button
          type="submit"
          className="px-3 py-1.5 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors"
        >
          เพิ่มสมาชิก
        </button>
      </form>

      <table className="w-full text-sm border">
        <thead>
          <tr className="bg-gray-50 text-left">
            <th className="p-2">เบอร์โทร</th>
            <th className="p-2">ชื่อ</th>
            <th className="p-2">แต้มสะสม</th>
            <th className="p-2"></th>
          </tr>
        </thead>
        <tbody>
          {customers.map((c) => (
            <tr key={c.id} className="border-t">
              {editingId === c.id ? (
                <>
                  <td className="p-2">
                    <input
                      value={editPhone}
                      onChange={(e) => setEditPhone(e.target.value)}
                      className="border rounded px-1 py-0.5 w-32"
                    />
                  </td>
                  <td className="p-2">
                    <input
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="border rounded px-1 py-0.5 w-full"
                    />
                  </td>
                  <td className="p-2">{c.points}</td>
                  <td className="p-2 text-right space-x-2">
                    <button onClick={saveEdit} className="text-amber-600">
                      บันทึก
                    </button>
                    <button onClick={() => setEditingId(null)} className="text-gray-500">
                      ยกเลิก
                    </button>
                  </td>
                </>
              ) : (
                <>
                  <td className="p-2">{c.phone}</td>
                  <td className="p-2">{c.name || "-"}</td>
                  <td className="p-2 font-medium">{c.points}</td>
                  <td className="p-2 text-right">
                    <button onClick={() => startEdit(c)} className="text-amber-600">
                      แก้ไข
                    </button>
                  </td>
                </>
              )}
            </tr>
          ))}
          {customers.length === 0 && (
            <tr>
              <td colSpan={4} className="p-2 text-gray-500">
                ยังไม่มีข้อมูลลูกค้า
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
