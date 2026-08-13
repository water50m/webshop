"use client";

import { CheckCircle2, Clock3, Eye, FileStack, LockKeyhole, RefreshCw, ShieldCheck } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { api, HistoryAnalysisBatch, HistoryAnalysisPreparation, HistoryPreparationStatus } from "@/lib/api";

export default function HistoryPreparationPage() {
  const [status, setStatus] = useState<HistoryPreparationStatus | null>(null);
  const [preparations, setPreparations] = useState<HistoryAnalysisPreparation[]>([]);
  const [selectedBatch, setSelectedBatch] = useState<HistoryAnalysisBatch | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [actingBatchId, setActingBatchId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextStatus, nextPreparations] = await Promise.all([
        api.getHistoryPreparationStatus(),
        api.listHistoryAnalysisPreparations(),
      ]);
      setStatus(nextStatus);
      setPreparations(nextPreparations);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  async function createPreparation() {
    setCreating(true);
    try {
      const preparation = await api.createHistoryAnalysisPreparation();
      setPreparations((current) => [preparation, ...current]);
      setSelectedBatch(null);
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setCreating(false);
    }
  }

  async function viewBatch(batchId: number) {
    setActingBatchId(batchId);
    try {
      setSelectedBatch(await api.getHistoryAnalysisBatch(batchId));
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setActingBatchId(null);
    }
  }

  async function approveBatch(batchId: number) {
    setActingBatchId(batchId);
    try {
      const approved = await api.approveHistoryAnalysisBatch(batchId);
      setSelectedBatch(approved);
      await load();
    } catch (err) {
      setError(String(err));
    } finally {
      setActingBatchId(null);
    }
  }

  const ready = status?.state === "ready";

  return (
    <main className="mx-auto w-full max-w-3xl p-5 md:p-8">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">เตรียมข้อมูลแชต</h1>
          <p className="mt-1 text-slate-600">พื้นที่แยกสำหรับวิเคราะห์ประวัติ Facebook เพื่อสร้าง Script ในอนาคต</p>
        </div>
        <button onClick={() => void load()} className="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-50" title="ตรวจสอบอีกครั้ง">
          <RefreshCw className={`h-5 w-5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && <p className="mb-4 rounded-lg bg-red-50 p-3 text-red-700">{error}</p>}
      {status && (
        <>
          <section className={`rounded-xl border p-5 ${ready ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"}`}>
            <div className="flex items-center gap-3">
              {ready ? <CheckCircle2 className="h-7 w-7 text-emerald-600" /> : <Clock3 className="h-7 w-7 text-amber-600" />}
              <div>
                <h2 className="font-semibold">{ready ? "พร้อมเริ่มวิเคราะห์" : "กำลังรอ token"}</h2>
                <p className="text-sm text-slate-700">{status.next_action}</p>
              </div>
            </div>
          </section>

          <section className="mt-4 grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-slate-200 p-4"><p className="text-xs text-slate-500">แหล่งข้อมูล</p><p className="mt-1 font-medium">Facebook ย้อนหลัง {status.lookback_days} วัน</p></div>
            <div className="rounded-xl border border-slate-200 p-4"><p className="text-xs text-slate-500">Page ID</p><p className="mt-1 font-medium">{status.page_id_ready ? "ตั้งค่าแล้ว" : "จะตรวจจาก token เมื่อเริ่มงาน"}</p></div>
          </section>

          <section className="mt-4 rounded-xl border border-slate-200 p-5">
            <div className="flex items-center gap-2 font-semibold text-slate-900"><LockKeyhole className="h-4 w-4" /> ขอบเขตความปลอดภัย</div>
            <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-slate-600">
              <li>อ่านและวิเคราะห์ข้อมูลเท่านั้น</li>
              <li>ไม่มี endpoint หรือสิทธิ์สำหรับส่งข้อความหาลูกค้า</li>
              <li>ผลลัพธ์จะเป็นร่าง Script, FAQ และกฎการรับออเดอร์เพื่อให้ตรวจทานภายหลัง</li>
            </ul>
          </section>

          <section className="mt-4 rounded-xl border border-slate-200 p-5">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 font-semibold text-slate-900"><FileStack className="h-4 w-4" /> ชุดข้อมูลสำหรับตรวจทาน</div>
                <p className="mt-1 text-sm text-slate-600">สร้างสำเนาข้อความที่ปกปิดข้อมูลส่วนบุคคลแล้วในเครื่อง ก่อนอนุมัติเป็นรายชุด</p>
              </div>
              <button
                onClick={() => void createPreparation()}
                disabled={creating}
                className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {creating ? "กำลังสร้าง..." : "สร้างชุดข้อมูลปกปิด"}
              </button>
            </div>

            {preparations.length === 0 ? (
              <p className="mt-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">ยังไม่มีชุดข้อมูลที่เตรียมไว้</p>
            ) : (
              <div className="mt-4 space-y-4">
                {preparations.map((preparation) => (
                  <div key={preparation.id} className="rounded-lg border border-slate-200 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div>
                        <p className="font-medium text-slate-900">Snapshot #{preparation.id}</p>
                        <p className="text-sm text-slate-600">{preparation.conversation_count} บทสนทนา · {preparation.message_count} ข้อความ · {preparation.batch_count} ชุดย่อย</p>
                      </div>
                      <p className="text-xs text-slate-500">{new Date(preparation.created_at).toLocaleString("th-TH")}</p>
                    </div>
                    {Object.keys(preparation.redaction_counts).length > 0 && (
                      <p className="mt-2 text-xs text-slate-500">ปกปิดแล้ว: {Object.entries(preparation.redaction_counts).map(([kind, count]) => `${kind} ${count}`).join(" · ")}</p>
                    )}
                    <div className="mt-3 grid gap-2 sm:grid-cols-2">
                      {preparation.batches.map((batch) => (
                        <div key={batch.id} className="flex items-center justify-between gap-2 rounded-md bg-slate-50 p-3 text-sm">
                          <div>
                            <p className="font-medium">ชุด {batch.batch_number} <span className={batch.status === "approved" ? "text-emerald-700" : "text-amber-700"}>· {batch.status === "approved" ? "อนุมัติแล้ว" : "รอตรวจ"}</span></p>
                            <p className="text-xs text-slate-500">{batch.conversation_count} บทสนทนา · {batch.message_count} ข้อความ</p>
                          </div>
                          <div className="flex gap-1">
                            <button onClick={() => void viewBatch(batch.id)} disabled={actingBatchId === batch.id} className="rounded p-2 text-slate-600 hover:bg-white" title="ดูตัวอย่าง"><Eye className="h-4 w-4" /></button>
                            {batch.status !== "approved" && <button onClick={() => void approveBatch(batch.id)} disabled={actingBatchId === batch.id} className="rounded p-2 text-emerald-700 hover:bg-white" title="อนุมัติชุดนี้"><ShieldCheck className="h-4 w-4" /></button>}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {selectedBatch && (
            <section className="mt-4 rounded-xl border border-slate-200 p-5">
              <div className="flex items-center justify-between gap-3">
                <div><h2 className="font-semibold text-slate-900">ตัวอย่างชุด {selectedBatch.batch_number}</h2><p className="text-sm text-slate-600">แสดงเฉพาะข้อความที่ปกปิดแล้ว ไม่มีรหัส Facebook, ชื่อลูกค้า หรือเวลาจริง</p></div>
                <span className={selectedBatch.status === "approved" ? "text-sm text-emerald-700" : "text-sm text-amber-700"}>{selectedBatch.status === "approved" ? "อนุมัติแล้ว" : "รอตรวจ"}</span>
              </div>
              <div className="mt-4 max-h-[32rem] space-y-4 overflow-y-auto rounded-lg bg-slate-50 p-4">
                {selectedBatch.content.conversations.map((conversation) => (
                  <div key={conversation.conversation}>
                    <p className="mb-2 text-xs font-medium text-slate-500">{conversation.conversation}</p>
                    <div className="space-y-2">
                      {conversation.messages.map((message, index) => <p key={`${conversation.conversation}-${index}`} className={`rounded-lg px-3 py-2 text-sm ${message.speaker === "customer" ? "bg-white text-slate-800" : "ml-5 bg-slate-200 text-slate-700"}`}><span className="mr-2 text-xs font-medium text-slate-500">{message.speaker === "customer" ? "ลูกค้า" : "ร้าน"}</span>{message.text}</p>)}
                    </div>
                  </div>
                ))}
              </div>
              {selectedBatch.status !== "approved" && <button onClick={() => void approveBatch(selectedBatch.id)} disabled={actingBatchId === selectedBatch.id} className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-60">อนุมัติชุดนี้เพื่อใช้วิเคราะห์ในขั้นถัดไป</button>}
              <p className="mt-3 text-xs text-slate-500">การอนุมัติทำหน้าที่เปลี่ยนสถานะในเครื่องเท่านั้น ยังไม่มีการส่งข้อมูลให้ผู้ให้บริการ AI</p>
            </section>
          )}
        </>
      )}
    </main>
  );
}
