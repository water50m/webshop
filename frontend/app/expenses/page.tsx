"use client";

import { Receipt } from "lucide-react";
import { useEffect, useState } from "react";
import { api, Expense, ExpenseCategory } from "@/lib/api";

const CATEGORY_LABELS: Record<ExpenseCategory, string> = {
  cost_of_goods: "ค่าสินค้า",
  shipping: "ค่าขนส่ง",
  rent: "ค่าเช่า",
  utilities: "ค่าน้ำ/ค่าไฟ",
  marketing: "ค่าโฆษณา",
  other: "อื่นๆ",
};

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function ExpensesPage() {
  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [category, setCategory] = useState<ExpenseCategory>("cost_of_goods");
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const [expenseDate, setExpenseDate] = useState(today());

  function reload() {
    api.listExpenses().then(setExpenses).catch((e) => setError(String(e)));
  }

  useEffect(() => {
    reload();
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    await api.createExpense({
      category,
      amount: Number(amount),
      description,
      expense_date: expenseDate,
    });
    setAmount("");
    setDescription("");
    reload();
  }

  async function handleDelete(id: number) {
    await api.deleteExpense(id);
    reload();
  }

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <Receipt className="w-5 h-5 text-amber-500" />
        รายจ่าย
      </h1>
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <form onSubmit={handleSubmit} className="flex flex-wrap gap-2 mb-6 items-end">
        <select
          value={category}
          onChange={(e) => setCategory(e.target.value as ExpenseCategory)}
          className="border rounded px-2 py-1"
        >
          {Object.entries(CATEGORY_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
        <input
          type="number"
          step="0.01"
          required
          placeholder="จำนวนเงิน"
          value={amount}
          onChange={(e) => setAmount(e.target.value)}
          className="border rounded px-2 py-1 w-32"
        />
        <input
          type="text"
          placeholder="รายละเอียด"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="border rounded px-2 py-1 flex-1"
        />
        <input
          type="date"
          required
          value={expenseDate}
          onChange={(e) => setExpenseDate(e.target.value)}
          className="border rounded px-2 py-1"
        />
        <button type="submit" className="px-4 py-1 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors">
          เพิ่ม
        </button>
      </form>

      <table className="w-full text-sm border">
        <thead>
          <tr className="bg-gray-50 text-left">
            <th className="p-2">วันที่</th>
            <th className="p-2">หมวด</th>
            <th className="p-2">รายละเอียด</th>
            <th className="p-2">จำนวนเงิน</th>
            <th className="p-2"></th>
          </tr>
        </thead>
        <tbody>
          {expenses.map((expense) => (
            <tr key={expense.id} className="border-t hover:bg-amber-50 transition-colors">
              <td className="p-2">{expense.expense_date}</td>
              <td className="p-2">{CATEGORY_LABELS[expense.category]}</td>
              <td className="p-2 text-gray-500">{expense.description}</td>
              <td className="p-2">{expense.amount.toLocaleString()}</td>
              <td className="p-2">
                <button
                  onClick={() => handleDelete(expense.id)}
                  className="text-red-600 hover:underline"
                >
                  ลบ
                </button>
              </td>
            </tr>
          ))}
          {expenses.length === 0 && !error && (
            <tr>
              <td colSpan={5} className="p-2 text-gray-500">
                ยังไม่มีรายจ่าย
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </main>
  );
}
