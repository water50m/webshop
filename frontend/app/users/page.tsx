"use client";

import { Users as UsersIcon, Trash2, Pencil, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError, AuthUser, UserRole } from "@/lib/api";
import { useAuth } from "@/lib/auth";

const ROLE_LABEL: Record<UserRole, string> = {
  owner: "เจ้าของร้าน",
  manager: "ผู้จัดการ",
  cashier: "แคชเชียร์",
};

export default function UsersPage() {
  const { user: currentUser } = useAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [modalUser, setModalUser] = useState<AuthUser | "new" | null>(null);

  function reload() {
    api
      .listUsers()
      .then(setUsers)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }

  useEffect(() => {
    reload();
  }, []);

  async function handleDelete(id: number) {
    if (!confirm("ยืนยันลบผู้ใช้นี้?")) return;
    await api.deleteUser(id);
    reload();
  }

  if (currentUser && currentUser.role !== "owner") {
    return (
      <div className="p-8 text-sm text-slate-500">หน้านี้สำหรับเจ้าของร้านเท่านั้น</div>
    );
  }

  return (
    <div className="p-4 md:p-8 lg:p-10">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold text-slate-800 flex items-center gap-2">
          <UsersIcon className="w-5 h-5 text-amber-500" />
          จัดการผู้ใช้งาน
        </h1>
        <button
          onClick={() => setModalUser("new")}
          className="flex items-center gap-1.5 bg-amber-500 hover:bg-amber-600 text-white text-sm font-medium px-3 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          เพิ่มผู้ใช้
        </button>
      </div>

      {error && <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>}

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-slate-500 text-left">
            <tr>
              <th className="px-4 py-2.5 font-medium">ชื่อผู้ใช้</th>
              <th className="px-4 py-2.5 font-medium">ชื่อที่แสดง</th>
              <th className="px-4 py-2.5 font-medium">บทบาท</th>
              <th className="px-4 py-2.5 font-medium w-20"></th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-t border-slate-100 hover:bg-slate-50">
                <td className="px-4 py-2.5 text-slate-800">{u.username}</td>
                <td className="px-4 py-2.5 text-slate-600">{u.display_name}</td>
                <td className="px-4 py-2.5 text-slate-600">{ROLE_LABEL[u.role]}</td>
                <td className="px-4 py-2.5 flex items-center gap-2">
                  <button onClick={() => setModalUser(u)} className="text-slate-400 hover:text-amber-600">
                    <Pencil className="w-4 h-4" />
                  </button>
                  {u.id !== currentUser?.id && (
                    <button onClick={() => handleDelete(u.id)} className="text-slate-400 hover:text-red-600">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modalUser && (
        <UserModal
          user={modalUser === "new" ? null : modalUser}
          onClose={() => setModalUser(null)}
          onSaved={() => {
            setModalUser(null);
            reload();
          }}
        />
      )}
    </div>
  );
}

function UserModal({
  user,
  onClose,
  onSaved,
}: {
  user: AuthUser | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [username, setUsername] = useState(user?.username ?? "");
  const [displayName, setDisplayName] = useState(user?.display_name ?? "");
  const [role, setRole] = useState<UserRole>(user?.role ?? "cashier");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (user) {
        await api.updateUser(user.id, { display_name: displayName, role, password: password || null });
      } else {
        await api.createUser({ username, password, display_name: displayName, role });
      }
      onSaved();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "บันทึกไม่สำเร็จ");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 p-4">
      <form onSubmit={handleSubmit} className="bg-white rounded-xl shadow-lg w-full max-w-sm p-6">
        <h2 className="text-lg font-semibold text-slate-800 mb-4">{user ? "แก้ไขผู้ใช้" : "เพิ่มผู้ใช้ใหม่"}</h2>

        {error && <div className="mb-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>}

        <label className="block text-sm font-medium text-slate-700 mb-1">ชื่อผู้ใช้ (login)</label>
        <input
          value={username}
          disabled={!!user}
          onChange={(e) => setUsername(e.target.value)}
          className="w-full mb-3 rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-amber-400"
        />

        <label className="block text-sm font-medium text-slate-700 mb-1">ชื่อที่แสดง</label>
        <input
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full mb-3 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
        />

        <label className="block text-sm font-medium text-slate-700 mb-1">บทบาท</label>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value as UserRole)}
          className="w-full mb-3 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
        >
          <option value="cashier">แคชเชียร์</option>
          <option value="manager">ผู้จัดการ</option>
          <option value="owner">เจ้าของร้าน</option>
        </select>

        <label className="block text-sm font-medium text-slate-700 mb-1">
          {user ? "รหัสผ่านใหม่ (เว้นว่างถ้าไม่เปลี่ยน)" : "รหัสผ่าน"}
        </label>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full mb-6 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400"
        />

        <div className="flex gap-2 justify-end">
          <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 rounded-lg">
            ยกเลิก
          </button>
          <button
            type="submit"
            disabled={submitting}
            className="px-4 py-2 text-sm bg-amber-500 hover:bg-amber-600 disabled:opacity-60 text-white font-medium rounded-lg"
          >
            บันทึก
          </button>
        </div>
      </form>
    </div>
  );
}
