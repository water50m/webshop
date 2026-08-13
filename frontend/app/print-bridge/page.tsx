"use client";

import { Bluetooth, CheckCircle2, CircleAlert, PlugZap, Plus, RefreshCw, Router, Wifi } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api, ApiError, CreatedPrintBridge, PrintBridge, PrintBridgeCommand } from "@/lib/api";

type BluetoothDevice = { name?: string; address?: string; rssi?: number };

const commandLabels: Record<string, string> = {
  scan_bluetooth: "ค้นหา Bluetooth",
  connect_printer: "เชื่อมต่อเครื่องพิมพ์",
  reconnect_printer: "เชื่อมต่อเครื่องพิมพ์ใหม่",
  test_printer: "ทดสอบพิมพ์",
  test_bridge: "ทดสอบ Bridge",
  configure_wifi: "ตั้งค่า Wi-Fi",
};

function Status({ ok, label }: { ok: boolean; label: string }) {
  const Icon = ok ? CheckCircle2 : CircleAlert;
  return <span className={`inline-flex items-center gap-1.5 text-sm ${ok ? "text-emerald-700" : "text-slate-500"}`}><Icon className="w-4 h-4" />{label}</span>;
}

export default function PrintBridgePage() {
  const [bridges, setBridges] = useState<PrintBridge[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [commands, setCommands] = useState<PrintBridgeCommand[]>([]);
  const [name, setName] = useState("");
  const [wifiSsid, setWifiSsid] = useState("");
  const [wifiPassword, setWifiPassword] = useState("");
  const [created, setCreated] = useState<CreatedPrintBridge | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = bridges.find((bridge) => bridge.id === selectedId) ?? null;
  const scan = commands.find((command) => command.command === "scan_bluetooth" && command.status === "succeeded");
  const devices = Array.isArray(scan?.result.devices) ? scan.result.devices as BluetoothDevice[] : [];

  const refresh = useCallback(async () => {
    try {
      const rows = await api.listPrintBridges();
      setBridges(rows);
      setSelectedId((current) => current ?? rows[0]?.id ?? null);
      const id = selectedId ?? rows[0]?.id;
      if (id) setCommands(await api.listPrintBridgeCommands(id));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [selectedId]);

  useEffect(() => {
    const timer = window.setTimeout(() => { void refresh(); }, 0);
    return () => window.clearTimeout(timer);
  }, [refresh]);
  useEffect(() => {
    if (!selectedId) return;
    api.listPrintBridgeCommands(selectedId).then(setCommands).catch(() => {});
  }, [selectedId]);
  useEffect(() => {
    const timer = window.setInterval(() => { void refresh(); }, 5000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function createBridge(event: FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setBusy("create"); setError(null);
    try {
      const bridge = await api.createPrintBridge(name.trim());
      setCreated(bridge); setName(""); setSelectedId(bridge.id);
      await refresh();
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(null); }
  }

  async function queue(command: string, payload: Record<string, unknown> = {}) {
    if (!selected) return;
    setBusy(command); setError(null);
    try {
      await api.sendPrintBridgeCommand(selected.id, command, payload);
      if (command === "configure_wifi") { setWifiPassword(""); }
      await refresh();
    } catch (e) { setError(e instanceof ApiError ? e.message : String(e)); }
    finally { setBusy(null); }
  }

  function showLastSeen(value: string | null) {
    return value ? new Date(value).toLocaleString("th-TH") : "ยังไม่เคยติดต่อ";
  }

  return <main className="p-4 md:p-6 lg:p-8 max-w-6xl w-full">
    <div className="flex flex-wrap justify-between gap-3 mb-6">
      <div><h1 className="text-xl font-semibold flex items-center gap-2"><Router className="w-5 h-5 text-amber-500" />จัดการ Print Bridge</h1>
      <p className="text-sm text-slate-500 mt-1">ESP32 เชื่อมออกหา backend เพื่อรับคำสั่ง — ไม่ต้องเปิด server หรือ port จากภายนอก</p></div>
      <button onClick={() => void refresh()} className="px-3 py-2 rounded border text-sm hover:bg-slate-50 flex items-center gap-2"><RefreshCw className="w-4 h-4" />รีเฟรช</button>
    </div>
    {error && <p className="mb-4 rounded-lg bg-red-50 text-red-700 px-3 py-2 text-sm">{error}</p>}

    {created && <section className="mb-5 border border-amber-300 bg-amber-50 rounded-xl p-4">
      <div className="font-medium text-amber-900">สร้าง {created.name} แล้ว — คัดลอก Device Token ไปใส่ใน ESP32 ตอนตั้งค่า</div>
      <code className="block mt-2 break-all rounded bg-white border border-amber-200 p-2 text-xs text-slate-700">{created.device_token}</code>
      <p className="text-xs text-amber-800 mt-2">Token นี้แสดงครั้งเดียว เก็บไว้เป็นความลับและห้ามใส่ในหน้าเว็บสาธารณะ</p>
      <button onClick={() => setCreated(null)} className="text-sm underline mt-2 text-amber-900">ปิด</button>
    </section>}

    <div className="grid lg:grid-cols-[280px_1fr] gap-5">
      <aside className="space-y-3"><form onSubmit={createBridge} className="border rounded-xl p-3 bg-white">
        <label className="text-sm font-medium">เพิ่ม ESP32 Bridge</label>
        <input value={name} onChange={(event) => setName(event.target.value)} placeholder="เช่น เคาน์เตอร์หน้า" className="border rounded px-2 py-2 w-full mt-2 text-sm" />
        <button disabled={busy === "create"} className="mt-2 w-full px-3 py-2 rounded bg-amber-500 text-white text-sm flex justify-center gap-2 disabled:opacity-50"><Plus className="w-4 h-4" />เพิ่ม Bridge</button>
      </form>
      {loading ? <p className="text-sm text-slate-500">กำลังโหลด...</p> : bridges.map((bridge) => <button key={bridge.id} onClick={() => setSelectedId(bridge.id)} className={`w-full text-left border rounded-xl p-3 transition ${selectedId === bridge.id ? "border-amber-400 bg-amber-50" : "bg-white hover:border-slate-300"}`}>
        <div className="font-medium text-sm">{bridge.name}</div><div className="mt-1"><Status ok={bridge.is_online} label={bridge.is_online ? "Bridge ออนไลน์" : "Bridge ออฟไลน์"} /></div>
      </button>)}</aside>

      <section>{selected ? <div className="space-y-4">
        <div className="grid sm:grid-cols-2 gap-3"><div className="border rounded-xl p-4 bg-white"><div className="flex items-center gap-2 font-medium mb-3"><PlugZap className="w-5 h-5 text-amber-500" />Backend ↔ Bridge</div><Status ok={selected.is_online} label={selected.is_online ? "ส่งข้อมูลถึงกันได้" : "ยังติดต่อ Bridge ไม่ได้"} /><p className="text-xs text-slate-500 mt-3">ติดต่อครั้งล่าสุด: {showLastSeen(selected.last_seen_at)}</p><p className="text-xs text-slate-500">Firmware: {selected.firmware_version || "ไม่ระบุ"}</p>
          <button onClick={() => void queue("test_bridge")} disabled={!!busy} className="mt-3 px-3 py-1.5 rounded border text-sm hover:bg-slate-50 disabled:opacity-50">{busy === "test_bridge" ? "กำลังส่ง..." : "ทดสอบ Bridge"}</button></div>
        <div className="border rounded-xl p-4 bg-white"><div className="flex items-center gap-2 font-medium mb-3"><Bluetooth className="w-5 h-5 text-blue-600" />Bridge ↔ เครื่องพิมพ์</div><Status ok={selected.printer_connected} label={selected.printer_connected ? "เชื่อมต่อเครื่องพิมพ์แล้ว" : "ยังไม่เชื่อมต่อเครื่องพิมพ์"} /><p className="text-xs text-slate-500 mt-3">{selected.printer_name || "ยังไม่ได้เลือกเครื่องพิมพ์"}{selected.printer_address && ` · ${selected.printer_address}`}</p>{selected.printer_error && <p className="text-xs text-red-600 mt-1">{selected.printer_error}</p>}
          <div className="flex flex-wrap gap-2 mt-3"><button onClick={() => void queue("reconnect_printer")} disabled={!!busy} className="px-3 py-1.5 rounded border text-sm disabled:opacity-50">Reconnect</button><button onClick={() => void queue("test_printer")} disabled={!!busy} className="px-3 py-1.5 rounded bg-slate-800 text-white text-sm disabled:opacity-50">ทดสอบพิมพ์</button></div></div></div>

        <div className="grid xl:grid-cols-2 gap-4"><section className="border rounded-xl p-4 bg-white"><div className="flex justify-between gap-2 items-center"><h2 className="font-medium flex items-center gap-2"><Bluetooth className="w-5 h-5 text-blue-600" />ค้นหา Bluetooth</h2><button onClick={() => void queue("scan_bluetooth")} disabled={!!busy} className="px-3 py-1.5 rounded border text-sm disabled:opacity-50">{busy === "scan_bluetooth" ? "กำลังค้นหา..." : "ค้นหา"}</button></div>
          <p className="text-xs text-slate-500 mt-1">ผลค้นหาจะมาเมื่อ ESP32 ประมวลผลคำสั่งเสร็จ</p><div className="mt-3 space-y-2">{devices.length ? devices.map((device, index) => <div key={`${device.address}-${index}`} className="border rounded-lg p-2 flex justify-between gap-3 text-sm"><div><div>{device.name || "ไม่ทราบชื่อ"}</div><div className="text-xs text-slate-500">{device.address || "ไม่พบ address"}{device.rssi !== undefined && ` · ${device.rssi} dBm`}</div></div><button onClick={() => void queue("connect_printer", { address: device.address, name: device.name ?? "" })} disabled={!device.address || !!busy} className="text-amber-700 text-xs font-medium disabled:opacity-50">เชื่อมต่อ</button></div>) : <p className="text-sm text-slate-400 py-3">ยังไม่มีผลการค้นหา</p>}</div></section>
        <section className="border rounded-xl p-4 bg-white"><h2 className="font-medium flex items-center gap-2"><Wifi className="w-5 h-5 text-sky-600" />เปลี่ยน Wi-Fi ของ Bridge</h2><p className="text-xs text-amber-700 mt-1">เมื่อเปลี่ยนแล้ว Bridge อาจออฟไลน์ชั่วคราว หากตั้งค่าไม่สำเร็จให้ใช้ปุ่ม Provisioning บน ESP32</p><input value={wifiSsid} onChange={(event) => setWifiSsid(event.target.value)} placeholder="ชื่อ Wi-Fi (SSID)" className="border rounded px-2 py-2 w-full mt-3 text-sm" /><input value={wifiPassword} onChange={(event) => setWifiPassword(event.target.value)} type="password" placeholder="รหัสผ่าน Wi-Fi" className="border rounded px-2 py-2 w-full mt-2 text-sm" /><button onClick={() => void queue("configure_wifi", { ssid: wifiSsid, password: wifiPassword })} disabled={!wifiSsid || !wifiPassword || !!busy} className="mt-2 px-3 py-2 rounded bg-amber-500 text-white text-sm disabled:opacity-50">ส่งการตั้งค่า Wi-Fi</button></section></div>

        <section className="border rounded-xl p-4 bg-white"><h2 className="font-medium mb-3">ประวัติคำสั่งล่าสุด</h2><div className="space-y-2">{commands.length ? commands.map((command) => <div key={command.id} className="text-sm border-b last:border-0 pb-2 last:pb-0 flex flex-wrap justify-between gap-2"><span>{commandLabels[command.command] ?? command.command}</span><span className={command.status === "failed" ? "text-red-600" : command.status === "succeeded" ? "text-emerald-700" : "text-slate-500"}>{command.status === "succeeded" ? "สำเร็จ" : command.status === "failed" ? "ไม่สำเร็จ" : command.status === "delivered" ? "กำลังทำงาน" : "รอ Bridge รับงาน"}</span></div>) : <p className="text-sm text-slate-400">ยังไม่มีคำสั่ง</p>}</div></section>
      </div> : <div className="border rounded-xl p-8 text-center text-slate-500">เพิ่ม Print Bridge เพื่อเริ่มตั้งค่า</div>}</section>
    </div>
  </main>;
}
