"use client";

import { Settings as SettingsIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { api, ApiError, DbConfig, DbEngine, ShopSettings } from "@/lib/api";
import { useAuth } from "@/lib/auth";

export default function SettingsPage() {
  const { user } = useAuth();
  const [settings, setSettings] = useState<ShopSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [lineTestResult, setLineTestResult] = useState<string | null>(null);
  const [testingLine, setTestingLine] = useState(false);

  const [dbConfig, setDbConfig] = useState<DbConfig | null>(null);
  const [dbEngine, setDbEngine] = useState<DbEngine>("sqlite");
  const [dbSqlitePath, setDbSqlitePath] = useState("./dev.db");
  const [dbPostgresUrl, setDbPostgresUrl] = useState("");
  const [dbTestResult, setDbTestResult] = useState<string | null>(null);
  const [dbTesting, setDbTesting] = useState(false);
  const [dbSaving, setDbSaving] = useState(false);
  const [dbSaved, setDbSaved] = useState(false);

  useEffect(() => {
    api
      .getSettings()
      .then(setSettings)
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (user?.role !== "owner") return;
    api
      .getDbConfig()
      .then((cfg) => {
        setDbConfig(cfg);
        setDbEngine(cfg.engine);
        setDbSqlitePath(cfg.sqlite_path);
        setDbPostgresUrl(cfg.postgres_url);
      })
      .catch(() => {});
  }, [user]);

  function update(patch: Partial<ShopSettings>) {
    setSettings((prev) => (prev ? { ...prev, ...patch } : prev));
    setSaved(false);
  }

  async function handleSave() {
    if (!settings) return;
    await api.updateSettings(settings);
    setSaved(true);
  }

  function dbPayload() {
    return { engine: dbEngine, sqlite_path: dbSqlitePath, postgres_url: dbPostgresUrl };
  }

  async function handleTestDbConfig() {
    setDbTesting(true);
    setDbTestResult(null);
    try {
      const res = await api.testDbConfig(dbPayload());
      setDbTestResult(res.detail);
    } catch (e) {
      setDbTestResult(e instanceof ApiError ? e.message : String(e));
    } finally {
      setDbTesting(false);
    }
  }

  async function handleSaveDbConfig() {
    setDbSaving(true);
    setDbSaved(false);
    try {
      const cfg = await api.updateDbConfig(dbPayload());
      setDbConfig(cfg);
      setDbSaved(true);
    } catch (e) {
      setDbTestResult(e instanceof ApiError ? e.message : String(e));
    } finally {
      setDbSaving(false);
    }
  }

  async function handleTestLineNotify() {
    setTestingLine(true);
    setLineTestResult(null);
    try {
      const res = await api.testLineNotify();
      setLineTestResult(res.detail);
    } catch (e) {
      setLineTestResult(e instanceof ApiError ? e.message : String(e));
    } finally {
      setTestingLine(false);
    }
  }

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
        <SettingsIcon className="w-5 h-5 text-amber-500" />
        ตั้งค่าร้าน
      </h1>
      {user?.role === "owner" && <a href="/facebook" className="mb-4 inline-flex rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm font-medium text-blue-700 hover:bg-blue-100">เชื่อม Facebook Page</a>}
      {error && <p className="text-red-600 mb-4">{error}</p>}
      {settings && (
        <div className="space-y-4">
          <div className="columns-1 md:columns-2 xl:columns-3 2xl:columns-4 gap-4">
            <section className="bg-white rounded-xl border border-slate-200 p-4 mb-4 break-inside-avoid">
              <p className="text-sm text-gray-600 mb-2">
                ประเภทร้าน (มีผลต่อสูตรคำนวณภาษีในหน้าสรุปกำไร-ขาดทุน)
              </p>
              <label className="flex items-center gap-2 mb-1">
                <input
                  type="radio"
                  name="shop_type"
                  checked={settings.shop_type === "individual"}
                  onChange={() => update({ shop_type: "individual" })}
                  className="accent-amber-500"
                />
                บุคคลธรรมดา
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="radio"
                  name="shop_type"
                  checked={settings.shop_type === "juristic"}
                  onChange={() => update({ shop_type: "juristic" })}
                  className="accent-amber-500"
                />
                นิติบุคคล (บริษัท/ห้างหุ้นส่วน)
              </label>
            </section>

            <section className="bg-white rounded-xl border border-slate-200 p-4 mb-4 break-inside-avoid">
              <p className="text-sm text-gray-600 mb-2">
                ข้อมูลร้านสำหรับแสดงบนใบเสร็จ
              </p>
              <label className="block text-xs text-gray-500 mb-1">ชื่อร้าน</label>
              <input
                type="text"
                value={settings.shop_name}
                onChange={(e) => update({ shop_name: e.target.value })}
                className="border rounded px-2 py-1.5 w-full mb-3"
              />
              <label className="block text-xs text-gray-500 mb-1">ที่อยู่</label>
              <textarea
                value={settings.address}
                onChange={(e) => update({ address: e.target.value })}
                className="border rounded px-2 py-1.5 w-full mb-3"
                rows={2}
              />
              <label className="block text-xs text-gray-500 mb-1">เลขประจำตัวผู้เสียภาษี (ไม่บังคับ)</label>
              <input
                type="text"
                value={settings.tax_id}
                onChange={(e) => update({ tax_id: e.target.value })}
                className="border rounded px-2 py-1.5 w-full"
              />
            </section>

            <section className="bg-white rounded-xl border border-slate-200 p-4 mb-4 break-inside-avoid">
              <p className="text-sm text-gray-600 mb-2">
                เลขพร้อมเพย์ (สำหรับสร้าง QR รับเงินโอนหน้าร้าน)
              </p>
              <label className="block text-xs text-gray-500 mb-1">
                เบอร์โทร 10 หลัก หรือเลขประจำตัวผู้เสียภาษี/บัตรประชาชน 13 หลัก
              </label>
              <input
                type="text"
                value={settings.promptpay_id}
                onChange={(e) => update({ promptpay_id: e.target.value })}
                placeholder="0812345678"
                className="border rounded px-2 py-1.5 w-full"
              />
            </section>

            <section className="bg-white rounded-xl border border-slate-200 p-4 mb-4 break-inside-avoid">
              <p className="text-sm text-gray-600 mb-2">ระบบสมาชิก/แต้มสะสม</p>
              <label className="block text-xs text-gray-500 mb-1">
                ยอดซื้อกี่บาทได้ 1 แต้ม (ใส่ 0 เพื่อปิดการสะสมแต้ม)
              </label>
              <input
                type="number"
                value={settings.loyalty_baht_per_point}
                onChange={(e) => update({ loyalty_baht_per_point: Number(e.target.value) })}
                className="border rounded px-2 py-1.5 w-full"
              />
              <p className="text-xs text-gray-400 mt-1">เมื่อชำระเงินใช้แต้มแลกได้ 1 แต้ม = 1 บาท</p>
            </section>

            <section className="bg-white rounded-xl border border-slate-200 p-4 mb-4 break-inside-avoid">
              <p className="text-sm text-gray-600 mb-2">
                แจ้งเตือนสต๊อกใกล้หมดผ่าน LINE (ต้องมี LINE Official Account + Messaging API ก่อน)
              </p>
              <label className="block text-xs text-gray-500 mb-1">Channel Access Token</label>
              <input
                type="text"
                value={settings.low_stock_line_token}
                onChange={(e) => update({ low_stock_line_token: e.target.value })}
                className="border rounded px-2 py-1.5 w-full mb-3"
              />
              <label className="block text-xs text-gray-500 mb-1">User/Group ID ปลายทาง</label>
              <input
                type="text"
                value={settings.low_stock_line_target_id}
                onChange={(e) => update({ low_stock_line_target_id: e.target.value })}
                className="border rounded px-2 py-1.5 w-full mb-3"
              />
              <button
                type="button"
                onClick={handleTestLineNotify}
                disabled={testingLine}
                className="px-3 py-1.5 rounded border text-sm hover:bg-gray-50 transition-colors disabled:opacity-50"
              >
                {testingLine ? "กำลังส่ง..." : "ทดสอบส่งแจ้งเตือน"}
              </button>
              {lineTestResult && <p className="text-xs mt-2 text-gray-600">{lineTestResult}</p>}
            </section>

            <section className="bg-white rounded-xl border border-slate-200 p-4 mb-4 break-inside-avoid">
              <p className="text-sm text-gray-600 mb-2">
                ระบบตัดสต๊อก (มีผลกับการขายสินค้าและรอบนับสต๊อก)
              </p>
              <label className="flex items-start gap-2 mb-2">
                <input
                  type="radio"
                  name="inventory_mode"
                  checked={settings.inventory_mode === "simple"}
                  onChange={() => update({ inventory_mode: "simple" })}
                  className="accent-amber-500 mt-0.5"
                />
                <span>
                  <span className="block">ขายปลีก (ตัดสต๊อกสินค้าโดยตรง)</span>
                  <span className="block text-xs text-gray-400">
                    ขายเท่าไหร่ ตัดสต๊อกของสินค้านั้นเท่านั้น เหมาะกับร้านที่ขายของสำเร็จเป็นหน่วย (เครื่องดื่มขวด, เบเกอรี่)
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2">
                <input
                  type="radio"
                  name="inventory_mode"
                  checked={settings.inventory_mode === "recipe"}
                  onChange={() => update({ inventory_mode: "recipe" })}
                  className="accent-amber-500 mt-0.5"
                />
                <span>
                  <span className="block">ร้านนั่งทาน/ครัว (ตัดสต๊อกตามสูตร/วัตถุดิบ)</span>
                  <span className="block text-xs text-gray-400">
                    ขายเมนูที่ตั้งสูตรไว้ จะตัดสต๊อกวัตถุดิบตามสูตรอัตโนมัติ (ตั้งสูตรได้ที่หน้า &quot;สินค้า/สต๊อก&quot;) —
                    สินค้าที่ไม่ได้ตั้งสูตรจะตัดสต๊อกของตัวเองตามปกติ
                  </span>
                </span>
              </label>
            </section>

            <section className="bg-white rounded-xl border border-slate-200 p-4 mb-4 break-inside-avoid">
              <p className="text-sm text-gray-600 mb-2">
                ระบบตีความข้อความสั่งซื้อจาก Meta/LINE (รับข้อความจากลูกค้าแล้วสร้าง draft order)
              </p>
              <label className="flex items-start gap-2 mb-2">
                <input
                  type="radio"
                  name="order_parser_mode"
                  checked={settings.order_parser_mode === "algorithm"}
                  onChange={() => update({ order_parser_mode: "algorithm" })}
                  className="accent-amber-500 mt-0.5"
                />
                <span>
                  <span className="block">Algorithm ดิบ (ค่าเริ่มต้น)</span>
                  <span className="block text-xs text-gray-400">
                    จับคู่คำแบบ keyword matching ทำงานทันที ไม่ต้องตั้งค่าเพิ่ม ไม่มีค่าใช้จ่าย แต่ไม่เข้าใจคำพ้องความหมาย/พิมพ์ผิด
                  </span>
                </span>
              </label>
              <label className="flex items-start gap-2">
                <input
                  type="radio"
                  name="order_parser_mode"
                  checked={settings.order_parser_mode === "ai"}
                  onChange={() => update({ order_parser_mode: "ai" })}
                  className="accent-amber-500 mt-0.5"
                />
                <span>
                  <span className="block">AI (ต้องใส่ API Key)</span>
                  <span className="block text-xs text-gray-400">
                    ส่งข้อความให้ AI ช่วยตีความ เข้าใจภาษาธรรมชาติได้กว้างกว่า มีค่าใช้จ่ายต่อข้อความ และถ้าเรียก AI ไม่สำเร็จ
                    (ไม่มี key/เน็ตล่ม) ระบบจะใช้ algorithm ดิบแทนให้อัตโนมัติ
                  </span>
                </span>
              </label>
              {settings.order_parser_mode === "ai" && (
                <>
                  <label className="block text-xs text-gray-500 mb-1 mt-3">AI API Key (Anthropic)</label>
                  <input
                    type="password"
                    value={settings.ai_api_key}
                    onChange={(e) => update({ ai_api_key: e.target.value })}
                    placeholder="sk-ant-..."
                    className="border rounded px-2 py-1.5 w-full"
                  />
                </>
              )}
            </section>

            <section className="bg-white rounded-xl border border-slate-200 p-4 mb-4 break-inside-avoid">
              <p className="text-sm text-gray-600 mb-2">
                เครื่องพิมพ์ใบเสร็จ (Thermal/Network printer) — เตรียมไว้รอเชื่อมต่อ
              </p>
              <label className="block text-xs text-gray-500 mb-1">IP เครื่องพิมพ์</label>
              <input
                type="text"
                value={settings.receipt_printer_ip}
                onChange={(e) => update({ receipt_printer_ip: e.target.value })}
                placeholder="192.168.1.50"
                className="border rounded px-2 py-1.5 w-full mb-3"
              />
              <label className="block text-xs text-gray-500 mb-1">พอร์ต (ปกติ 9100)</label>
              <input
                type="number"
                value={settings.receipt_printer_port}
                onChange={(e) => update({ receipt_printer_port: Number(e.target.value) })}
                className="border rounded px-2 py-1.5 w-full"
              />
              <p className="text-xs text-gray-400 mt-1">
                ปุ่ม &quot;พิมพ์ผ่านเครื่อง&quot; ในหน้าใบเสร็จจะส่งคำสั่งพิมพ์ ESC/POS ไปที่ IP นี้โดยตรง — ถ้ายังไม่มีเครื่องพิมพ์เชื่อมต่อ
                ระบบจะแจ้งว่าเชื่อมต่อไม่สำเร็จ ใช้ปุ่ม PDF แทนได้
              </p>
              <a href="/print-bridge" className="mt-3 inline-flex rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-100">
                จัดการ Print Bridge (ESP32)
              </a>
            </section>

            {user?.role === "owner" && dbConfig && (
              <section className="bg-white rounded-xl border border-slate-200 p-4 mb-4 break-inside-avoid">
                <p className="text-sm text-gray-600 mb-2">ฐานข้อมูล (ต้อง restart backend หลังเปลี่ยนถึงจะมีผล)</p>
                {dbConfig.env_override && (
                  <p className="text-xs text-amber-600 mb-2">
                    ตอนนี้มี environment variable <code>DATABASE_URL</code> ตั้งไว้ ซึ่งมีผลเหนือกว่าค่าที่ตั้งในหน้านี้เสมอ
                  </p>
                )}
                <label className="flex items-center gap-2 mb-1">
                  <input
                    type="radio"
                    name="db_engine"
                    checked={dbEngine === "sqlite"}
                    onChange={() => setDbEngine("sqlite")}
                    className="accent-amber-500"
                  />
                  SQLite (ไฟล์ในเครื่อง)
                </label>
                <label className="flex items-center gap-2 mb-2">
                  <input
                    type="radio"
                    name="db_engine"
                    checked={dbEngine === "postgres"}
                    onChange={() => setDbEngine("postgres")}
                    className="accent-amber-500"
                  />
                  PostgreSQL (เซิร์ฟเวอร์)
                </label>

                {dbEngine === "sqlite" ? (
                  <>
                    <label className="block text-xs text-gray-500 mb-1">ที่อยู่ไฟล์ SQLite</label>
                    <input
                      type="text"
                      value={dbSqlitePath}
                      onChange={(e) => setDbSqlitePath(e.target.value)}
                      placeholder="./dev.db"
                      className="border rounded px-2 py-1.5 w-full mb-2"
                    />
                  </>
                ) : (
                  <>
                    <label className="block text-xs text-gray-500 mb-1">Connection string</label>
                    <input
                      type="password"
                      value={dbPostgresUrl}
                      onChange={(e) => setDbPostgresUrl(e.target.value)}
                      placeholder="postgresql+psycopg2://user:pass@host:5432/dbname"
                      className="border rounded px-2 py-1.5 w-full mb-2"
                    />
                  </>
                )}

                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={handleTestDbConfig}
                    disabled={dbTesting}
                    className="px-3 py-1.5 rounded border text-sm hover:bg-gray-50 transition-colors disabled:opacity-50"
                  >
                    {dbTesting ? "กำลังทดสอบ..." : "ทดสอบการเชื่อมต่อ"}
                  </button>
                  <button
                    type="button"
                    onClick={handleSaveDbConfig}
                    disabled={dbSaving}
                    className="px-3 py-1.5 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors disabled:opacity-50"
                  >
                    {dbSaving ? "กำลังบันทึก..." : "บันทึกการตั้งค่าฐานข้อมูล"}
                  </button>
                </div>
                {dbTestResult && <p className="text-xs mt-2 text-gray-600">{dbTestResult}</p>}
                {dbSaved && (
                  <p className="text-xs mt-2 text-green-700">
                    บันทึกแล้ว — ต้อง restart backend (ปิด/เปิด process ใหม่) เพื่อให้เปลี่ยนไปใช้ฐานข้อมูลนี้จริง
                  </p>
                )}
              </section>
            )}
          </div>

          <div className="sticky bottom-0 bg-gray-50/80 backdrop-blur-sm py-3 flex items-center gap-3">
            <button
              onClick={handleSave}
              className="px-4 py-2 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors"
            >
              บันทึก
            </button>
            {saved && <p className="text-green-600 text-sm">บันทึกแล้ว</p>}
          </div>
        </div>
      )}
    </main>
  );
}
