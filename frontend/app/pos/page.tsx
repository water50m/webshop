"use client";

import { FileDown, LayoutDashboard, Plus, Printer, QrCode, Trash2, Undo2, WifiOff } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, Customer, PaymentMethod, Product, resolveImageUrl, Sale, Shift, ShiftSummary } from "@/lib/api";
import { dequeue, enqueue, getQueue, queueForSale } from "@/lib/offlineQueue";
import { downloadReceiptPdf } from "@/lib/receiptPdf";
import Receipt from "../components/Receipt";

function modifierLabel(item: { modifiers: { name: string; price_delta: number }[] }): string {
  if (item.modifiers.length === 0) return "";
  return item.modifiers.map((m) => m.name).join(", ");
}

function modSignature(mods: { name: string }[]): string {
  return mods.map((m) => m.name).slice().sort().join("|");
}

type LastItemAction =
  | { kind: "synced"; itemId: number; prevQuantity: number; label: string }
  | { kind: "pending"; tempId: string; queueId: string; label: string };

function money(n: number): string {
  return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

type PaymentRow = { method: PaymentMethod; amount: string };

export default function PosPage() {
  const [shift, setShift] = useState<Shift | null | undefined>(undefined); // undefined = loading
  const [openingCash, setOpeningCash] = useState("0");

  const [closingShift, setClosingShift] = useState<ShiftSummary | null>(null);
  const [closingCashCounted, setClosingCashCounted] = useState("");

  const [heldSales, setHeldSales] = useState<Sale[]>([]);
  const [activeSale, setActiveSale] = useState<Sale | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [search, setSearch] = useState("");
  const [products, setProducts] = useState<Product[]>([]);
  const [productFilter, setProductFilter] = useState("");
  const [categories, setCategories] = useState<string[]>([]);
  const [categoryFilter, setCategoryFilter] = useState("");
  const scanRef = useRef<HTMLInputElement>(null);

  const [billDiscount, setBillDiscount] = useState("");
  const [billLabel, setBillLabel] = useState("");
  const [payments, setPayments] = useState<PaymentRow[]>([{ method: "cash", amount: "" }]);

  const [receipt, setReceipt] = useState<Sale | null>(null);
  const receiptRef = useRef<HTMLDivElement>(null);
  const [printingThermal, setPrintingThermal] = useState(false);
  const [printError, setPrintError] = useState<string | null>(null);

  async function handleDownloadPdf() {
    if (!receiptRef.current || !receipt) return;
    await downloadReceiptPdf(receiptRef.current, `receipt-${receipt.receipt_no ?? receipt.id}.pdf`);
  }

  async function handlePrintThermal() {
    if (!receipt) return;
    setPrintingThermal(true);
    setPrintError(null);
    try {
      await api.printReceiptThermal(receipt.id);
    } catch (e) {
      setPrintError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setPrintingThermal(false);
    }
  }

  const [modifierPicker, setModifierPicker] = useState<Product | null>(null);
  const [selectedModifierIds, setSelectedModifierIds] = useState<number[]>([]);

  const [customerPhone, setCustomerPhone] = useState("");
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [customerError, setCustomerError] = useState<string | null>(null);
  const [redeemPoints, setRedeemPoints] = useState("");

  const [isOnline, setIsOnline] = useState(true);
  const [pendingItems, setPendingItems] = useState<
    { tempId: string; product: Product; quantity: number; modifierIds: number[] }[]
  >([]);

  const [lastItemAction, setLastItemAction] = useState<LastItemAction | null>(null);

  function isNetworkError(e: unknown): boolean {
    return !(e instanceof ApiError);
  }

  function showError(e: unknown) {
    setError(e instanceof ApiError ? e.message : String(e));
  }

  async function loadShift() {
    try {
      const current = await api.getCurrentShift();
      setShift(current);
    } catch (e) {
      showError(e);
    }
  }

  async function handleOpenShift(e: React.FormEvent) {
    e.preventDefault();
    try {
      const opened = await api.openShift(Number(openingCash) || 0);
      setShift(opened);
    } catch (e) {
      showError(e);
    }
  }

  async function openCloseShiftDialog() {
    if (!shift) return;
    try {
      const summary = await api.getShiftSummary(shift.id);
      setClosingCashCounted(String(summary.expected_cash.toFixed(2)));
      setClosingShift(summary);
    } catch (e) {
      showError(e);
    }
  }

  async function confirmCloseShift() {
    if (!shift) return;
    try {
      await api.closeShift(shift.id, Number(closingCashCounted) || 0);
      setClosingShift(null);
      setShift(null);
    } catch (e) {
      showError(e);
    }
  }

  async function refreshHeldSales(): Promise<Sale[]> {
    const list = await api.listHeldSales();
    setHeldSales(list);
    return list;
  }

  function resetPaymentRows(total: number) {
    setPayments([{ method: "cash", amount: total > 0 ? total.toFixed(2) : "" }]);
  }

  function refreshPendingItems(saleId: number, productList: Product[]) {
    const queued = queueForSale(saleId);
    setPendingItems(
      queued.flatMap((a) => {
        const product = productList.find((p) => p.id === a.payload.product_id);
        if (!product) return [];
        return [{ tempId: a.tempId, product, quantity: a.payload.quantity ?? 1, modifierIds: a.payload.modifier_ids ?? [] }];
      })
    );
  }

  async function selectSale(id: number) {
    const sale = await api.getSale(id);
    setActiveSale(sale);
    setBillDiscount(String(sale.discount_amount || ""));
    setBillLabel(sale.note || "");
    resetPaymentRows(sale.total);
    setCustomerPhone("");
    setCustomer(null);
    setRedeemPoints("");
    setLastItemAction(null);
    refreshPendingItems(id, products);
  }

  async function replayQueue(saleId: number) {
    const queue = getQueue();
    let anyReplayed = false;
    for (const action of queue) {
      try {
        await api.addSaleItem(action.saleId, action.payload);
        dequeue(action.id);
        anyReplayed = true;
      } catch (e) {
        if (isNetworkError(e)) break; // still offline, retry next tick
        dequeue(action.id); // request itself is invalid (e.g. product deleted) — drop it
      }
    }
    if (anyReplayed && activeSale && activeSale.id === saleId) {
      try {
        const refreshed = await api.getSale(saleId);
        setActiveSale(refreshed);
        resetPaymentRows(refreshed.total);
      } catch {
        // ignore, will refresh next successful tick
      }
    }
    if (activeSale) refreshPendingItems(activeSale.id, products);
  }

  async function applyBillLabel() {
    if (!activeSale) return;
    const updated = await api.updateSale(activeSale.id, { note: billLabel });
    setActiveSale(updated);
    await refreshHeldSales();
  }

  async function newBill() {
    const sale = await api.createSale();
    await refreshHeldSales();
    await selectSale(sale.id);
  }

  useEffect(() => {
    const timer = window.setTimeout(() => void loadShift(), 0);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!shift) return;
    (async () => {
      try {
        const list = await refreshHeldSales();
        if (list.length > 0) {
          await selectSale(list[0].id);
        } else {
          await newBill();
        }
      } catch (e) {
        showError(e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shift]);

  function reloadProducts(term: string) {
    api.listProducts(term || undefined, false, categoryFilter || undefined).then(setProducts).catch(showError);
  }

  useEffect(() => {
    reloadProducts(productFilter);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryFilter]);

  useEffect(() => {
    api.listCategories().then(setCategories).catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    function goOnline() {
      setIsOnline(true);
      if (activeSale) replayQueue(activeSale.id);
    }
    function goOffline() {
      setIsOnline(false);
    }
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    const initialStateTimer = window.setTimeout(() => setIsOnline(navigator.onLine), 0);
    const interval = setInterval(async () => {
      try {
        await api.health();
        setIsOnline(true);
        if (activeSale && getQueue().length > 0) replayQueue(activeSale.id);
      } catch {
        setIsOnline(false);
      }
    }, 10000);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
      window.clearTimeout(initialStateTimer);
      clearInterval(interval);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSale?.id]);

  useEffect(() => {
    const timer = activeSale ? window.setTimeout(() => void refreshPendingItems(activeSale.id, products), 0) : undefined;
    return () => {
      if (timer !== undefined) window.clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [products]);

  async function addProductToCart(product: Product, modifierIds: number[] = []) {
    if (!activeSale) return;
    const modNames = product.modifiers.filter((m) => modifierIds.includes(m.id)).map((m) => m.name);
    const sig = modNames.slice().sort().join("|");
    const existing = activeSale.items.find((i) => i.product_id === product.id && modSignature(i.modifiers) === sig);
    const prevQuantity = existing ? existing.quantity : 0;
    try {
      const updated = await api.addSaleItem(activeSale.id, {
        product_id: product.id,
        quantity: 1,
        modifier_ids: modifierIds,
      });
      setActiveSale(updated);
      resetPaymentRows(updated.total);
      const matched = updated.items.find((i) => i.product_id === product.id && modSignature(i.modifiers) === sig);
      if (matched) {
        setLastItemAction({ kind: "synced", itemId: matched.id, prevQuantity, label: product.name });
      }
    } catch (e) {
      if (isNetworkError(e)) {
        const action = enqueue({
          type: "addItem",
          tempId: crypto.randomUUID(),
          saleId: activeSale.id,
          payload: { product_id: product.id, quantity: 1, modifier_ids: modifierIds },
        });
        setPendingItems((items) => [...items, { tempId: action.tempId, product, quantity: 1, modifierIds }]);
        setLastItemAction({ kind: "pending", tempId: action.tempId, queueId: action.id, label: product.name });
        setIsOnline(false);
      } else {
        showError(e);
      }
    }
  }

  function handleProductClick(product: Product) {
    if (product.modifiers.length > 0) {
      setModifierPicker(product);
      setSelectedModifierIds([]);
    } else {
      addProductToCart(product);
    }
  }

  function toggleModifierSelection(id: number) {
    setSelectedModifierIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
  }

  async function confirmModifierPicker() {
    if (!modifierPicker) return;
    await addProductToCart(modifierPicker, selectedModifierIds);
    setModifierPicker(null);
    setSelectedModifierIds([]);
  }

  async function handleScanSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!activeSale || !search.trim()) return;
    const code = search.trim();
    try {
      const product = await api.lookupProduct(code);
      if (product.modifiers.length > 0) {
        setModifierPicker(product);
        setSelectedModifierIds([]);
        setSearch("");
        return;
      }
      const existing = activeSale.items.find((i) => i.product_id === product.id && i.modifiers.length === 0);
      const prevQuantity = existing ? existing.quantity : 0;
      const updated = await api.addSaleItem(activeSale.id, { code, quantity: 1 });
      setActiveSale(updated);
      resetPaymentRows(updated.total);
      const matched = updated.items.find((i) => i.product_id === product.id && i.modifiers.length === 0);
      if (matched) {
        setLastItemAction({ kind: "synced", itemId: matched.id, prevQuantity, label: product.name });
      }
      setSearch("");
      reloadProducts("");
    } catch (e) {
      if (isNetworkError(e)) {
        const cached = products.find((p) => p.sku === code);
        if (cached) {
          setSearch("");
          if (cached.modifiers.length > 0) {
            setModifierPicker(cached);
            setSelectedModifierIds([]);
          } else {
            await addProductToCart(cached);
          }
        } else {
          setError("ออฟไลน์ - ไม่พบรหัสนี้ในแคชสินค้าที่โหลดไว้ล่าสุด");
        }
      } else {
        showError(e);
      }
    } finally {
      scanRef.current?.focus();
    }
  }

  async function changeQuantity(itemId: number, quantity: number) {
    if (!activeSale) return;
    const updated =
      quantity <= 0 ? await api.removeSaleItem(activeSale.id, itemId) : await api.updateSaleItem(activeSale.id, itemId, { quantity });
    setActiveSale(updated);
    resetPaymentRows(updated.total);
    if (lastItemAction?.kind === "synced" && lastItemAction.itemId === itemId) setLastItemAction(null);
  }

  async function removeItem(itemId: number) {
    if (!activeSale) return;
    const updated = await api.removeSaleItem(activeSale.id, itemId);
    setActiveSale(updated);
    resetPaymentRows(updated.total);
    if (lastItemAction?.kind === "synced" && lastItemAction.itemId === itemId) setLastItemAction(null);
  }

  async function undoLastItem() {
    if (!lastItemAction || !activeSale) return;
    if (lastItemAction.kind === "pending") {
      dequeue(lastItemAction.queueId);
      setPendingItems((items) => items.filter((i) => i.tempId !== lastItemAction.tempId));
      setLastItemAction(null);
      return;
    }
    try {
      const updated =
        lastItemAction.prevQuantity > 0
          ? await api.updateSaleItem(activeSale.id, lastItemAction.itemId, { quantity: lastItemAction.prevQuantity })
          : await api.removeSaleItem(activeSale.id, lastItemAction.itemId);
      setActiveSale(updated);
      resetPaymentRows(updated.total);
    } catch (e) {
      showError(e);
    } finally {
      setLastItemAction(null);
    }
  }

  async function applyBillDiscount() {
    if (!activeSale) return;
    const updated = await api.updateSale(activeSale.id, { discount_amount: Number(billDiscount) || 0 });
    setActiveSale(updated);
    resetPaymentRows(updated.total);
  }

  function updatePaymentRow(index: number, patch: Partial<PaymentRow>) {
    setPayments((rows) => rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  function addPaymentRow() {
    setPayments((rows) => [...rows, { method: "transfer", amount: "" }]);
  }

  function removePaymentRow(index: number) {
    setPayments((rows) => rows.filter((_, i) => i !== index));
  }

  const totalTendered = payments.reduce((sum, p) => sum + (Number(p.amount) || 0), 0);
  const effectiveTotal = activeSale ? Math.max(0, activeSale.total - (Number(redeemPoints) || 0)) : 0;
  const changeDue = activeSale ? totalTendered - effectiveTotal : 0;
  const checkoutDisabled =
    !activeSale ||
    activeSale.items.length === 0 ||
    totalTendered < effectiveTotal ||
    !isOnline ||
    pendingItems.length > 0;

  const cashRowIndex = payments.findIndex((p) => p.method === "cash");

  function setQuickCash(extra: number) {
    if (!activeSale || cashRowIndex === -1) return;
    const otherTendered = payments.reduce(
      (sum, p, i) => (i === cashRowIndex ? sum : sum + (Number(p.amount) || 0)),
      0
    );
    const amountDue = Math.max(0, effectiveTotal - otherTendered);
    updatePaymentRow(cashRowIndex, { amount: String(amountDue + extra) });
  }

  const [qrPayload, setQrPayload] = useState<string | null>(null);
  const [qrError, setQrError] = useState<string | null>(null);

  async function showTransferQr(index: number) {
    if (!activeSale) return;
    const row = payments[index];
    const otherTendered = payments.reduce(
      (sum, p, i) => (i === index ? sum : sum + (Number(p.amount) || 0)),
      0
    );
    const amount = Number(row.amount) || Math.max(0, effectiveTotal - otherTendered);
    setQrError(null);
    setQrPayload(null);
    try {
      const res = await api.getPromptPayQr(amount);
      setQrPayload(res.payload);
    } catch (e) {
      setQrError(e instanceof ApiError ? e.message : String(e));
    }
  }

  async function lookupCustomer() {
    setCustomerError(null);
    setCustomer(null);
    if (!customerPhone.trim()) return;
    try {
      const found = await api.lookupCustomer(customerPhone.trim());
      setCustomer(found);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) {
        setCustomerError("ไม่พบลูกค้าเบอร์นี้ — ระบบจะสร้างสมาชิกใหม่ให้ตอนชำระเงิน");
      } else {
        showError(e);
      }
    }
  }

  async function handleCheckout() {
    if (!activeSale) return;
    try {
      const completed = await api.checkoutSale(
        activeSale.id,
        payments.filter((p) => Number(p.amount) > 0).map((p) => ({ method: p.method, amount: Number(p.amount) })),
        customerPhone.trim()
          ? {
              customer_phone: customerPhone.trim(),
              redeem_points: Number(redeemPoints) || 0,
            }
          : {}
      );
      setReceipt(completed);
      setActiveSale(null);
      setLastItemAction(null);
      const remaining = await refreshHeldSales();
      if (remaining.length > 0) {
        await selectSale(remaining[0].id);
      } else {
        await newBill();
      }
    } catch (e) {
      showError(e);
    }
  }

  function holdCurrentBill() {
    setActiveSale(null);
    setLastItemAction(null);
  }

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null;
      const isTyping = !!target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName);

      if (e.key === "Escape") {
        if (modifierPicker) {
          setModifierPicker(null);
          setSelectedModifierIds([]);
        } else if (qrPayload || qrError) {
          setQrPayload(null);
          setQrError(null);
        } else if (closingShift) {
          setClosingShift(null);
        }
        return;
      }

      if (e.key === "F2") {
        e.preventDefault();
        scanRef.current?.focus();
        return;
      }

      if (e.key === "F8") {
        e.preventDefault();
        if (activeSale) holdCurrentBill();
        return;
      }

      if (e.key === "F9") {
        e.preventDefault();
        if (!checkoutDisabled) handleCheckout();
        return;
      }

      if (!isTyping && (e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        undoLastItem();
        return;
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeSale, modifierPicker, qrPayload, qrError, closingShift, checkoutDisabled, lastItemAction]);

  if (shift === undefined) {
    return <div className="p-8 text-sm text-slate-400">กำลังโหลด...</div>;
  }

  if (shift === null) {
    return (
      <main className="p-4 max-w-md mx-auto mt-16">
        <h1 className="text-xl font-semibold mb-4 flex items-center gap-2">
          <LayoutDashboard className="w-5 h-5 text-amber-500" />
          เปิดกะก่อนเริ่มขาย
        </h1>
        {error && <p className="text-red-600 mb-2 cursor-pointer" onClick={() => setError(null)}>{error}</p>}
        <form onSubmit={handleOpenShift} className="bg-white border rounded-xl p-5 space-y-3">
          <label className="block text-sm font-medium text-slate-700">เงินทอนตั้งต้นในลิ้นชัก (บาท)</label>
          <input
            type="number"
            value={openingCash}
            onChange={(e) => setOpeningCash(e.target.value)}
            className="border rounded px-3 py-2 w-full"
          />
          <button type="submit" className="w-full bg-amber-500 hover:bg-amber-600 text-white font-medium py-2.5 rounded-lg transition-colors">
            เปิดกะ
          </button>
        </form>
      </main>
    );
  }

  return (
    <>
      <main className="print:hidden p-4 lg:p-6 grid grid-cols-1 md:grid-cols-3 xl:grid-cols-4 gap-4">
        <section className="md:col-span-2 xl:col-span-3">
          <div className="flex items-center justify-between mb-3">
            <h1 className="text-xl font-semibold flex items-center gap-2">
              <LayoutDashboard className="w-5 h-5 text-amber-500" />
              หน้าขาย (POS)
            </h1>
            <button onClick={openCloseShiftDialog} className="text-sm border rounded-lg px-3 py-1.5 hover:bg-slate-50 transition-colors">
              ปิดกะ
            </button>
          </div>
          <p className="text-xs text-gray-400 mb-2">
            คีย์ลัด: F2 โฟกัสช่องสแกน · Ctrl+Z ยกเลิกรายการล่าสุด · F8 พักบิล · F9 ชำระเงิน · Esc ปิดหน้าต่าง
          </p>
          {!isOnline && (
            <div className="flex items-center gap-2 text-sm bg-amber-50 border border-amber-300 text-amber-700 rounded px-3 py-2 mb-2">
              <WifiOff className="w-4 h-4" />
              ออฟไลน์ - ยังสแกน/เพิ่มสินค้าต่อได้ ระบบจะคิวไว้และซิงค์อัตโนมัติเมื่อเชื่อมต่อกลับมา
              (ต้องรอเชื่อมต่อก่อนถึงจะกดชำระเงินได้)
            </div>
          )}
          {error && (
            <p className="text-red-600 mb-2 cursor-pointer" onClick={() => setError(null)}>
              {error}
            </p>
          )}

          <form onSubmit={handleScanSubmit} className="mb-3">
            <input
              ref={scanRef}
              autoFocus
              type="text"
              placeholder="สแกนบาร์โค้ด / พิมพ์ SKU แล้ว Enter"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="border rounded px-3 py-2 w-full"
            />
          </form>

          <input
            type="text"
            placeholder="ค้นหาสินค้าด้วยชื่อ/sku"
            value={productFilter}
            onChange={(e) => {
              setProductFilter(e.target.value);
              reloadProducts(e.target.value);
            }}
            className="border rounded px-2 py-1 w-full mb-2"
          />

          {categories.length > 0 && (
            <div className="flex gap-1.5 mb-3 flex-wrap">
              <button
                onClick={() => setCategoryFilter("")}
                className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                  categoryFilter === "" ? "bg-amber-500 text-white border-amber-500" : "hover:bg-amber-50"
                }`}
              >
                ทั้งหมด
              </button>
              {categories.map((c) => (
                <button
                  key={c}
                  onClick={() => setCategoryFilter(c)}
                  className={`px-2.5 py-1 rounded-full text-xs border transition-colors ${
                    categoryFilter === c ? "bg-amber-500 text-white border-amber-500" : "hover:bg-amber-50"
                  }`}
                >
                  {c}
                </button>
              ))}
            </div>
          )}

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7 gap-2">
            {products.map((product) => {
              const low = product.stock_quantity <= product.low_stock_threshold;
              return (
                <button
                  key={product.id}
                  onClick={() => handleProductClick(product)}
                  disabled={product.stock_quantity <= 0}
                  className={`border rounded-lg p-2 text-left transition-all hover:border-amber-300 hover:bg-amber-50 hover:shadow-sm disabled:opacity-40 ${
                    low ? "border-red-400" : ""
                  }`}
                >
                  {product.image_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={resolveImageUrl(product.image_url) ?? undefined}
                      alt={product.name}
                      className="w-full h-20 object-cover rounded mb-1"
                    />
                  ) : (
                    <div className="w-full h-20 bg-gray-50 rounded mb-1 flex items-center justify-center text-gray-300 text-xs">
                      ไม่มีรูป
                    </div>
                  )}
                  <div className="font-medium text-sm">{product.name}</div>
                  <div className="text-xs text-gray-500">{product.sku}</div>
                  {product.discounted_price !== null ? (
                    <div className="text-sm">
                      <span className="line-through text-gray-400 mr-1">{money(product.price)}</span>
                      <span className="text-amber-600 font-semibold">{money(product.discounted_price)}</span>
                    </div>
                  ) : (
                    <div className="text-sm">{money(product.price)} บาท</div>
                  )}
                  <div className={`text-xs ${low ? "text-red-600" : "text-gray-400"}`}>
                    คงเหลือ {product.stock_quantity}
                  </div>
                </button>
              );
            })}
          </div>
        </section>

        <section className="md:col-span-1 border rounded p-3 flex flex-col min-h-[60vh] md:h-[85vh]">
          <div className="flex gap-1 mb-2 flex-wrap">
            {heldSales.map((sale) => (
              <button
                key={sale.id}
                onClick={() => selectSale(sale.id)}
                className={`px-2 py-1 rounded text-sm border transition-colors ${
                  activeSale?.id === sale.id
                    ? "bg-amber-500 text-white border-amber-500"
                    : "hover:bg-amber-50"
                }`}
              >
                บิล #{sale.id}
                {sale.note ? ` · ${sale.note}` : ""}
              </button>
            ))}
            <button
              onClick={newBill}
              className="px-2 py-1 rounded text-sm border hover:bg-amber-50 transition-colors"
            >
              + บิลใหม่
            </button>
          </div>

          {!activeSale ? (
            <p className="text-gray-500">เลือกหรือสร้างบิล</p>
          ) : (
            <>
              <input
                type="text"
                placeholder="ชื่อลูกค้า/โต๊ะ (ไม่บังคับ)"
                value={billLabel}
                onChange={(e) => setBillLabel(e.target.value)}
                onBlur={applyBillLabel}
                className="border rounded px-2 py-1 w-full mb-2 text-sm"
              />
              {lastItemAction && (
                <button
                  onClick={undoLastItem}
                  className="flex items-center gap-1 text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1 mb-2 hover:bg-amber-100 transition-colors w-fit"
                >
                  <Undo2 className="w-3.5 h-3.5" />
                  ยกเลิก &quot;{lastItemAction.label}&quot; ที่เพิ่งเพิ่ม (Ctrl+Z)
                </button>
              )}
              <div className="flex-1 overflow-y-auto">
                <table className="w-full text-sm">
                  <tbody>
                    {activeSale.items.map((item) => (
                      <tr key={item.id} className="border-b">
                        <td className="py-1">
                          <div className="font-medium">{item.product_name}</div>
                          <div className="text-xs text-gray-500">
                            {item.sku}
                            {modifierLabel(item) && ` · ${modifierLabel(item)}`}
                          </div>
                        </td>
                        <td className="py-1">
                          <div className="flex items-center gap-1">
                            <button
                              onClick={() => changeQuantity(item.id, item.quantity - 1)}
                              className="border rounded w-6"
                            >
                              -
                            </button>
                            <span>{item.quantity}</span>
                            <button
                              onClick={() => changeQuantity(item.id, item.quantity + 1)}
                              className="border rounded w-6"
                            >
                              +
                            </button>
                          </div>
                        </td>
                        <td className="py-1 text-right">{money(item.line_total)}</td>
                        <td className="py-1 text-right">
                          <button onClick={() => removeItem(item.id)} className="text-red-600 text-xs">
                            ลบ
                          </button>
                        </td>
                      </tr>
                    ))}
                    {pendingItems.map((p) => (
                      <tr key={p.tempId} className="border-b bg-amber-50">
                        <td className="py-1">
                          <div className="font-medium flex items-center gap-1">
                            <WifiOff className="w-3 h-3 text-amber-600" />
                            {p.product.name}
                          </div>
                          <div className="text-xs text-amber-600">ออฟไลน์ - รอซิงค์</div>
                        </td>
                        <td className="py-1">{p.quantity}</td>
                        <td className="py-1 text-right">-</td>
                        <td className="py-1 text-right"></td>
                      </tr>
                    ))}
                    {activeSale.items.length === 0 && pendingItems.length === 0 && (
                      <tr>
                        <td colSpan={4} className="text-gray-500 py-2">
                          ยังไม่มีสินค้าในบิลนี้
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="border-t pt-2 mt-2 text-sm space-y-1">
                <div className="flex justify-between">
                  <span>ยอดรวม</span>
                  <span>{money(activeSale.subtotal)}</span>
                </div>
                {activeSale.promotion_discount > 0 && (
                  <div className="flex justify-between text-amber-600">
                    <span>ส่วนลดโปรโมชั่น (ซื้อคู่กัน)</span>
                    <span>-{money(activeSale.promotion_discount)}</span>
                  </div>
                )}
                <div className="flex items-center justify-between gap-2">
                  <span>ส่วนลดทั้งบิล</span>
                  <input
                    type="number"
                    value={billDiscount}
                    onChange={(e) => setBillDiscount(e.target.value)}
                    onBlur={applyBillDiscount}
                    className="border rounded px-1 py-0.5 w-20 text-right"
                  />
                </div>
                <div className="flex justify-between font-semibold text-base">
                  <span>ยอดสุทธิ</span>
                  <span>{money(activeSale.total)}</span>
                </div>

                <div className="border-t pt-2 space-y-1">
                  <div className="flex gap-2">
                    <input
                      type="text"
                      placeholder="เบอร์โทรลูกค้า (ไม่บังคับ, สำหรับแต้มสะสม)"
                      value={customerPhone}
                      onChange={(e) => {
                        setCustomerPhone(e.target.value);
                        setCustomer(null);
                        setCustomerError(null);
                      }}
                      onBlur={lookupCustomer}
                      className="border rounded px-2 py-1 flex-1 text-xs"
                    />
                  </div>
                  {customer && (
                    <div className="flex items-center justify-between text-xs text-gray-600">
                      <span>
                        {customer.name || "ลูกค้า"} — แต้มสะสม {customer.points} แต้ม
                      </span>
                      {customer.points > 0 && (
                        <span className="flex items-center gap-1">
                          ใช้แต้ม
                          <input
                            type="number"
                            min={0}
                            max={Math.min(customer.points, activeSale.total)}
                            value={redeemPoints}
                            onChange={(e) => setRedeemPoints(e.target.value)}
                            className="border rounded px-1 py-0.5 w-16 text-right"
                          />
                        </span>
                      )}
                    </div>
                  )}
                  {customerError && <p className="text-xs text-amber-600">{customerError}</p>}
                </div>

                <div className="space-y-1 pt-1">
                  {payments.map((row, idx) => (
                    <div key={idx} className="flex gap-2">
                      <select
                        value={row.method}
                        onChange={(e) => updatePaymentRow(idx, { method: e.target.value as PaymentMethod })}
                        className="border rounded px-2 py-1 flex-1"
                      >
                        <option value="cash">เงินสด</option>
                        <option value="transfer">โอน/พร้อมเพย์ (QR)</option>
                      </select>
                      <input
                        type="number"
                        placeholder="จำนวนเงิน"
                        value={row.amount}
                        onChange={(e) => updatePaymentRow(idx, { amount: e.target.value })}
                        className="border rounded px-2 py-1 w-24"
                      />
                      {row.method === "transfer" && (
                        <button
                          type="button"
                          onClick={() => showTransferQr(idx)}
                          className="text-amber-600 px-1"
                          title="แสดง QR พร้อมเพย์"
                        >
                          <QrCode className="w-4 h-4" />
                        </button>
                      )}
                      {payments.length > 1 && (
                        <button onClick={() => removePaymentRow(idx)} className="text-red-500 px-1">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  ))}
                  {cashRowIndex !== -1 && (
                    <div className="flex gap-1.5 pt-0.5">
                      {[0, 20, 50, 100, 500].map((extra) => (
                        <button
                          key={extra}
                          type="button"
                          onClick={() => setQuickCash(extra)}
                          className="px-2 py-1 rounded text-xs border hover:bg-amber-50 transition-colors"
                        >
                          {extra === 0 ? "พอดี" : `+${extra}`}
                        </button>
                      ))}
                    </div>
                  )}
                  <button
                    onClick={addPaymentRow}
                    className="text-xs flex items-center gap-1 text-amber-600 hover:text-amber-700"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    เพิ่มวิธีชำระเงิน (แบ่งจ่าย)
                  </button>
                </div>
                {changeDue > 0 && (
                  <div className="flex justify-between text-sm text-gray-600">
                    <span>เงินทอน</span>
                    <span>{money(changeDue)}</span>
                  </div>
                )}

                <div className="flex gap-2 pt-2">
                  <button
                    onClick={holdCurrentBill}
                    className="flex-1 px-3 py-2 rounded border hover:bg-amber-50 transition-colors"
                  >
                    พักบิล
                  </button>
                  <button
                    onClick={handleCheckout}
                    disabled={checkoutDisabled}
                    title={
                      !isOnline || pendingItems.length > 0
                        ? "ต้องเชื่อมต่อและซิงค์รายการที่คิวไว้ให้ครบก่อนชำระเงิน"
                        : undefined
                    }
                    className="flex-1 px-3 py-2 rounded bg-green-600 text-white hover:bg-green-700 transition-colors disabled:opacity-40"
                  >
                    ชำระเงิน
                  </button>
                </div>
              </div>
            </>
          )}
        </section>
      </main>

      {modifierPicker && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl p-5 w-full max-w-xs">
            <h2 className="text-lg font-semibold mb-1">{modifierPicker.name}</h2>
            <p className="text-xs text-gray-500 mb-3">เลือกตัวเลือกเสริม (เลือกได้หลายอย่าง)</p>
            <div className="space-y-1.5 mb-4 max-h-64 overflow-y-auto">
              {modifierPicker.modifiers.map((m) => (
                <label
                  key={m.id}
                  className="flex items-center justify-between text-sm border rounded px-2 py-1.5 cursor-pointer hover:bg-amber-50"
                >
                  <span className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={selectedModifierIds.includes(m.id)}
                      onChange={() => toggleModifierSelection(m.id)}
                    />
                    {m.name}
                  </span>
                  <span className="text-gray-500">
                    {m.price_delta >= 0 ? "+" : ""}
                    {money(m.price_delta)}
                  </span>
                </label>
              ))}
            </div>
            <div className="flex gap-2">
              <button
                onClick={() => setModifierPicker(null)}
                className="flex-1 px-3 py-2 rounded border hover:bg-gray-50 transition-colors"
              >
                ยกเลิก
              </button>
              <button
                onClick={confirmModifierPicker}
                className="flex-1 px-3 py-2 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors"
              >
                เพิ่มลงตะกร้า
              </button>
            </div>
          </div>
        </div>
      )}

      {(qrPayload || qrError) && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl p-5 w-full max-w-xs text-center">
            <h2 className="text-base font-semibold mb-3">สแกนจ่ายด้วยพร้อมเพย์</h2>
            {qrError ? (
              <p className="text-red-600 text-sm">{qrError}</p>
            ) : (
              qrPayload && (
                <div className="flex justify-center mb-2">
                  <QRCodeSVG value={qrPayload} size={220} />
                </div>
              )
            )}
            <button
              onClick={() => {
                setQrPayload(null);
                setQrError(null);
              }}
              className="mt-3 w-full px-3 py-2 rounded border hover:bg-gray-50 transition-colors"
            >
              ปิด
            </button>
          </div>
        </div>
      )}

      {receipt && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 print:bg-white print:p-0 z-50">
          <div>
            <Receipt ref={receiptRef} sale={receipt} />
            {printError && <p className="text-red-600 text-xs mt-2 print:hidden">{printError}</p>}
            <div className="flex gap-2 mt-4 print:hidden">
              <button
                onClick={handleDownloadPdf}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded border hover:bg-gray-50 transition-colors"
              >
                <FileDown className="w-4 h-4" />
                PDF
              </button>
              <button
                onClick={handlePrintThermal}
                disabled={printingThermal}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors disabled:opacity-50"
              >
                <Printer className="w-4 h-4" />
                {printingThermal ? "กำลังพิมพ์..." : "พิมพ์ผ่านเครื่อง"}
              </button>
              <button
                onClick={() => {
                  setReceipt(null);
                  setPrintError(null);
                }}
                className="px-3 py-2 rounded border hover:bg-gray-50 transition-colors"
              >
                ปิด
              </button>
            </div>
          </div>
        </div>
      )}

      {closingShift && shift && (
        <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50">
          <div className="bg-white rounded-xl p-6 w-full max-w-sm">
            <h2 className="text-lg font-semibold mb-3">สรุปยอดท้ายกะ</h2>
            <div className="text-sm space-y-1 mb-4">
              <div className="flex justify-between">
                <span>จำนวนบิลที่ขาย</span>
                <span>{closingShift.sale_count}</span>
              </div>
              <div className="flex justify-between">
                <span>ยอดขายรวม</span>
                <span>{money(closingShift.total_revenue)}</span>
              </div>
              {Object.entries(closingShift.totals_by_method).map(([method, amt]) => (
                <div key={method} className="flex justify-between text-gray-500">
                  <span>{method === "cash" ? "เงินสด" : method === "transfer" ? "โอน/พร้อมเพย์" : method}</span>
                  <span>{money(amt)}</span>
                </div>
              ))}
              <div className="flex justify-between border-t pt-1">
                <span>เงินทอนตั้งต้น</span>
                <span>{money(closingShift.opening_cash)}</span>
              </div>
              <div className="flex justify-between font-medium">
                <span>เงินสดที่ควรมีในลิ้นชัก</span>
                <span>{money(closingShift.expected_cash)}</span>
              </div>
            </div>
            <label className="block text-sm font-medium text-slate-700 mb-1">นับเงินสดได้จริง (บาท)</label>
            <input
              type="number"
              value={closingCashCounted}
              onChange={(e) => setClosingCashCounted(e.target.value)}
              className="border rounded px-3 py-2 w-full mb-4"
            />
            <div className="flex gap-2">
              <button
                onClick={() => setClosingShift(null)}
                className="flex-1 px-3 py-2 rounded border hover:bg-gray-50 transition-colors"
              >
                ยกเลิก
              </button>
              <button
                onClick={confirmCloseShift}
                className="flex-1 px-3 py-2 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors"
              >
                ยืนยันปิดกะ
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
