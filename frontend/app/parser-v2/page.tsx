"use client";

import { ClipboardCheck, FlaskConical, RefreshCw, Send, ShieldAlert, Tags } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  api,
  ApiError,
  ParserV2Handoff,
  ParserV2HistorySummary,
  ParserV2Result,
  Product,
  ProductAlias,
} from "@/lib/api";

const DEFAULT_TEST_TEXT = "เอาข้าวหมกไก่ทอด 2 กล่อง";

function message(err: unknown) {
  return err instanceof ApiError ? err.message : "ทำรายการไม่สำเร็จ";
}

export default function ParserV2Page() {
  const [text, setText] = useState(DEFAULT_TEST_TEXT);
  const [conversationId, setConversationId] = useState("");
  const [result, setResult] = useState<ParserV2Result | null>(null);
  const [summary, setSummary] = useState<ParserV2HistorySummary | null>(null);
  const [handoffs, setHandoffs] = useState<ParserV2Handoff[]>([]);
  const [aliases, setAliases] = useState<ProductAlias[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [testing, setTesting] = useState(false);
  const [aliasText, setAliasText] = useState("");
  const [aliasProductId, setAliasProductId] = useState("");
  const [savingAlias, setSavingAlias] = useState(false);
  const [resolutions, setResolutions] = useState<Record<number, string>>({});
  const [resolvingId, setResolvingId] = useState<number | null>(null);
  const [confirmingDeliveryContext, setConfirmingDeliveryContext] = useState(false);
  const [resettingConversationState, setResettingConversationState] = useState(false);

  const productById = useMemo(() => new Map(products.map((product) => [product.id, product])), [products]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextSummary, nextHandoffs, nextAliases, nextProducts] = await Promise.all([
        api.getParserV2HistorySummary(),
        api.listParserV2Handoffs(),
        api.listProductAliases(),
        api.listProducts(),
      ]);
      setSummary(nextSummary);
      setHandoffs(nextHandoffs);
      setAliases(nextAliases);
      setProducts(nextProducts);
      setAliasProductId((current) => current || String(nextProducts[0]?.id ?? ""));
      setError(null);
    } catch (err) {
      setError(message(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void Promise.resolve().then(load);
  }, [load]);

  async function testParser(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    setTesting(true);
    try {
      const parsedConversationId = Number(conversationId);
      const nextResult = conversationId.trim()
        ? await api.testParserV2ConversationTurn(parsedConversationId, text)
        : await api.testParserV2(text);
      setResult(nextResult);
      setHandoffs(await api.listParserV2Handoffs());
      setError(null);
    } catch (err) {
      setError(message(err));
    } finally {
      setTesting(false);
    }
  }

  async function confirmDeliveryContext() {
    if (!result?.conversation_state || confirmingDeliveryContext) return;
    setConfirmingDeliveryContext(true);
    try {
      const conversationState = await api.confirmParserV2DeliveryContext(result.conversation_state.conversation_id);
      setResult((current) => current ? { ...current, conversation_state: conversationState } : current);
      setError(null);
    } catch (err) {
      setError(message(err));
    } finally {
      setConfirmingDeliveryContext(false);
    }
  }

  async function resetConversationState() {
    if (!result?.conversation_state || resettingConversationState) return;
    setResettingConversationState(true);
    try {
      const conversationState = await api.resetParserV2ConversationState(result.conversation_state.conversation_id);
      setResult((current) => current ? { ...current, conversation_state: conversationState } : current);
      setError(null);
    } catch (err) {
      setError(message(err));
    } finally {
      setResettingConversationState(false);
    }
  }

  async function saveAlias(event: FormEvent) {
    event.preventDefault();
    if (!aliasProductId || !aliasText.trim()) return;
    setSavingAlias(true);
    try {
      const alias = await api.createProductAlias(Number(aliasProductId), aliasText.trim());
      setAliases((current) => [...current, alias].sort((a, b) => a.alias_text.localeCompare(b.alias_text, "th")));
      setAliasText("");
      setError(null);
    } catch (err) {
      setError(message(err));
    } finally {
      setSavingAlias(false);
    }
  }

  async function resolveHandoff(handoff: ParserV2Handoff) {
    const resolution = resolutions[handoff.id]?.trim();
    if (!resolution) return;
    setResolvingId(handoff.id);
    try {
      const resolved = await api.resolveParserV2Handoff(handoff.id, resolution);
      setHandoffs((current) => current.map((row) => (row.id === resolved.id ? resolved : row)));
      setResolutions((current) => ({ ...current, [handoff.id]: "" }));
      setError(null);
    } catch (err) {
      setError(message(err));
    } finally {
      setResolvingId(null);
    }
  }

  return (
    <main className="mx-auto w-full max-w-6xl p-5 md:p-8">
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-slate-900"><FlaskConical className="h-6 w-6 text-violet-600" /> ทดลอง Parser v2</h1>
          <p className="mt-1 text-slate-600">โหมดแยกสำหรับตรวจผลกฎและตัดสินใจโดยแอดมิน — ไม่สร้างออเดอร์และไม่ส่งข้อความ Facebook</p>
        </div>
        <button onClick={() => void load()} className="rounded-lg border border-slate-200 p-2 text-slate-600 hover:bg-slate-50" title="โหลดข้อมูลใหม่">
          <RefreshCw className={`h-5 w-5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>

      {error && <p className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">{error}</p>}

      <section className="rounded-xl border border-violet-200 bg-violet-50 p-4 text-sm text-violet-950">
        <div className="flex gap-2"><ShieldAlert className="mt-0.5 h-4 w-4 shrink-0" /><p>ข้อความที่ต้องให้แอดมินตัดสินจะบันทึกเฉพาะฉบับที่ปกปิดข้อมูลแล้ว พร้อมเหตุผลและคำตอบแอดมิน เพื่อใช้ปรับกฎภายหลัง</p></div>
      </section>

      <section className="mt-4 grid gap-4 lg:grid-cols-[1.1fr,0.9fr]">
        <form onSubmit={testParser} className="rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-900">ลองอ่านข้อความ</h2>
          <p className="mt-1 text-sm text-slate-600">เว้นรหัสบทสนทนาไว้เพื่อทดสอบข้อความเดี่ยว; ใส่รหัสจาก Inbox เพื่อทดสอบ state ต่อเนื่อง โดยไม่สร้างข้อความหรือออเดอร์จริง</p>
          <input value={conversationId} onChange={(event) => setConversationId(event.target.value.replace(/\D/g, ""))} inputMode="numeric" placeholder="รหัสบทสนทนา (ไม่บังคับ)" className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100" />
          <textarea value={text} onChange={(event) => setText(event.target.value)} rows={5} maxLength={4000} className="mt-4 w-full rounded-lg border border-slate-300 p-3 text-sm outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-100" />
          <button disabled={testing || !text.trim()} className="mt-3 inline-flex items-center gap-2 rounded-lg bg-violet-700 px-4 py-2 text-sm font-medium text-white hover:bg-violet-800 disabled:opacity-60">
            <Send className="h-4 w-4" /> {testing ? "กำลังวิเคราะห์..." : "ทดสอบกฎ"}
          </button>

          {result && (
            <div className="mt-5 rounded-lg bg-slate-50 p-4 text-sm">
              <div className="grid gap-2 sm:grid-cols-2"><p><span className="text-slate-500">Intent:</span> <b>{result.intent}</b></p><p><span className="text-slate-500">ขั้นถัดไป:</span> <b>{result.next_state}</b></p></div>
              <p className="mt-2 break-words text-slate-600">ข้อความมาตรฐาน: {result.normalized_text || "—"}</p>
              {result.answer_text && <p className="mt-2 rounded bg-emerald-100 px-2 py-1 text-emerald-950">คำตอบที่ระบบส่งได้: {result.answer_text}</p>}
              {result.handoff_reason && <p className="mt-2 rounded bg-amber-100 px-2 py-1 text-amber-900">ส่งต่อแอดมิน: {result.handoff_reason}</p>}
              {result.items.length > 0 && <div className="mt-3 space-y-2">{result.items.map((item) => <div key={`${item.product_id}-${item.matched_text}`} className="rounded bg-white p-2"><b>{item.product_name}</b> × {item.quantity} · {item.packaging === "box" ? "กล่อง" : "ห่อ"} <span className="text-xs text-slate-500">({item.match_source})</span>{item.fallback_product_name && <p className="mt-1 text-xs text-slate-600">หาก {item.product_name} หมด → ใช้ {item.fallback_product_name} แทน</p>}{item.substitution_from && <p className="mt-1 text-xs text-amber-700">ใช้แทน {item.substitution_from} เพราะสินค้าหลักหมด</p>}</div>)}</div>}
              {result.candidates.length > 0 && <div className="mt-3 text-slate-600">ตัวเลือกที่คล้าย: {result.candidates.map((candidate) => `${candidate.product_name} (${candidate.score})`).join(", ")}</div>}
              {result.conversation_state && <div className="mt-3 rounded bg-violet-50 p-2 text-violet-950"><p>State บทสนทนา #{result.conversation_state.conversation_id}: <b>{result.conversation_state.state}</b></p>{result.conversation_state.last_items.length > 0 && <p className="mt-1 text-xs">รายการล่าสุด: {result.conversation_state.last_items.map((item) => `${item.product_name} × ${item.quantity}`).join(", ")}</p>}<div className="mt-2 flex flex-wrap gap-2"><button type="button" onClick={() => void confirmDeliveryContext()} disabled={confirmingDeliveryContext || result.conversation_state.delivery_context_confirmed} className="rounded border border-violet-300 bg-white px-2 py-1 text-xs disabled:opacity-50">{result.conversation_state.delivery_context_confirmed ? "ยืนยันจุดส่งเดิมแล้ว" : "ผู้ดูแลยืนยันให้ใช้จุดส่งเดิม"}</button><button type="button" onClick={() => void resetConversationState()} disabled={resettingConversationState} className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-700 disabled:opacity-50">ล้าง state การทดลอง</button></div></div>}
              {result.handoff_id && <p className="mt-3 text-xs text-slate-500">บันทึกส่งต่อแอดมิน #{result.handoff_id} แล้ว (ข้อความที่เก็บถูกปกปิด)</p>}
            </div>
          )}
        </form>

        <section className="rounded-xl border border-slate-200 p-5">
          <h2 className="flex items-center gap-2 font-semibold text-slate-900"><ClipboardCheck className="h-4 w-4" /> Baseline จากประวัติที่อนุมัติ</h2>
          {summary ? <div className="mt-4 grid grid-cols-2 gap-3 text-sm"><Metric label="ข้อความลูกค้า" value={summary.customer_message_count} /><Metric label="ชุดที่อนุมัติ" value={summary.approved_batch_count} /><Metric label="ต้องรอแอดมิน" value={summary.next_state_counts.waiting_for_admin ?? 0} /><Metric label="สินค้า match ได้" value={Object.values(summary.match_source_counts).reduce((sum, value) => sum + value, 0)} /></div> : <p className="mt-3 text-sm text-slate-500">กำลังโหลด…</p>}
          <p className="mt-4 text-xs text-slate-500">แสดงตัวเลขรวมจากข้อความที่ปกปิดและอนุมัติแล้วเท่านั้น ไม่มีข้อความประวัติแสดงในหน้านี้</p>
        </section>
      </section>

      <section className="mt-4 grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200 p-5">
          <h2 className="flex items-center gap-2 font-semibold text-slate-900"><Tags className="h-4 w-4" /> Alias ที่ผู้ดูแลอนุมัติ</h2>
          <form onSubmit={saveAlias} className="mt-3 grid gap-2 sm:grid-cols-[1fr,1fr,auto]">
            <select value={aliasProductId} onChange={(event) => setAliasProductId(event.target.value)} className="rounded-lg border border-slate-300 px-3 py-2 text-sm"><option value="">เลือกสินค้า</option>{products.map((product) => <option key={product.id} value={product.id}>{product.name}</option>)}</select>
            <input value={aliasText} onChange={(event) => setAliasText(event.target.value)} maxLength={255} placeholder="ชื่อเรียก/คำสะกดที่อนุมัติ" className="rounded-lg border border-slate-300 px-3 py-2 text-sm" />
            <button disabled={savingAlias || !aliasProductId || !aliasText.trim()} className="rounded-lg bg-slate-900 px-3 py-2 text-sm text-white disabled:opacity-60">เพิ่ม</button>
          </form>
          <div className="mt-4 space-y-2">{aliases.length === 0 ? <p className="text-sm text-slate-500">ยังไม่มี alias</p> : aliases.map((alias) => <div key={alias.id} className="flex items-center justify-between rounded-lg bg-slate-50 p-2 text-sm"><span>{alias.alias_text}</span><span className="text-slate-500">→ {productById.get(alias.product_id)?.name ?? `สินค้า #${alias.product_id}`}</span></div>)}</div>
        </section>

        <section className="rounded-xl border border-slate-200 p-5">
          <h2 className="font-semibold text-slate-900">รายการรอคำตอบแอดมิน</h2>
          <div className="mt-3 max-h-[30rem] space-y-3 overflow-y-auto">
            {handoffs.length === 0 ? <p className="text-sm text-slate-500">ยังไม่มีรายการส่งต่อ</p> : handoffs.map((handoff) => <div key={handoff.id} className="rounded-lg border border-slate-200 p-3 text-sm"><div className="flex items-start justify-between gap-2"><p className="break-words text-slate-700">{handoff.redacted_text}</p><span className={handoff.status === "resolved" ? "shrink-0 text-emerald-700" : "shrink-0 text-amber-700"}>{handoff.status === "resolved" ? "ปิดแล้ว" : "รอ"}</span></div><p className="mt-1 text-xs text-slate-500">{handoff.intent} · {handoff.reason}</p>{handoff.status === "resolved" ? <p className="mt-2 rounded bg-emerald-50 p-2 text-emerald-900">{handoff.resolution}</p> : <div className="mt-2 flex gap-2"><input value={resolutions[handoff.id] ?? ""} onChange={(event) => setResolutions((current) => ({ ...current, [handoff.id]: event.target.value }))} placeholder="คำตัดสิน/คำตอบของแอดมิน" className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1.5" /><button onClick={() => void resolveHandoff(handoff)} disabled={resolvingId === handoff.id || !(resolutions[handoff.id] ?? "").trim()} className="rounded bg-emerald-700 px-2 py-1.5 text-white disabled:opacity-50">บันทึก</button></div>}</div>)}</div>
        </section>
      </section>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return <div className="rounded-lg bg-slate-50 p-3"><p className="text-xs text-slate-500">{label}</p><p className="mt-1 text-lg font-semibold text-slate-900">{value.toLocaleString("th-TH")}</p></div>;
}
