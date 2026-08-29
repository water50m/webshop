"use client";

import { ArrowLeft, Camera, CircleUserRound, Eye, EyeOff, ImageOff, Inbox as InboxIcon, MapPin, Menu, Pin, PinOff, RefreshCw, Search, Send, Tag, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, Conversation, ConversationStatus, DraftOrder, FacebookConnection, InboxMessageEvent, Message, Product, resolveImageUrl } from "@/lib/api";
import { useMobileNav } from "@/app/components/MobileNavContext";

type VisibilityFilter = "active" | "hidden" | "all";

const STATUS_OPTIONS: { value: ConversationStatus; label: string; className: string }[] = [
  { value: "waiting_reply", label: "รอการตอบกลับ", className: "bg-rose-100 text-rose-700" },
  { value: "open", label: "รอดำเนินการ", className: "bg-blue-100 text-blue-700" },
  { value: "in_progress", label: "กำลังดูแล", className: "bg-amber-100 text-amber-800" },
  { value: "done", label: "เสร็จสิ้น", className: "bg-emerald-100 text-emerald-700" },
  { value: "spam", label: "ไม่เกี่ยวข้อง", className: "bg-gray-200 text-gray-600" },
];
const PRIMARY_LABEL_OPTIONS = ["รอแอดมิน", "ดำเนินการ", "รับออเดอร์แล้ว", "รอส่ง", "ส่งแล้ว", "เสร็จสิ้น", "แก้ไข"];
const PAYMENT_LABEL_OPTIONS = ["รอจ่ายเงิน", "จ่ายเงินแล้ว"];
const ORDER_REVIEW_ACKNOWLEDGEMENT = "ได้รับรายการแล้ว กำลังตรวจสอบก่อนยืนยันครับ";

const PRIMARY_LABEL_STYLES: Record<string, string> = {
  "รอแอดมิน": "border-violet-300 bg-violet-50 text-violet-700",
  "ดำเนินการ": "border-indigo-300 bg-indigo-50 text-indigo-700",
  "รับออเดอร์แล้ว": "border-blue-300 bg-blue-50 text-blue-700",
  "รอส่ง": "border-amber-300 bg-amber-50 text-amber-800",
  "ส่งแล้ว": "border-emerald-300 bg-emerald-50 text-emerald-700",
  "เสร็จสิ้น": "border-teal-300 bg-teal-50 text-teal-700",
  "แก้ไข": "border-rose-300 bg-rose-50 text-rose-700",
};

const PRIMARY_LABEL_COLORS: Record<string, string> = {
  "รอแอดมิน": "#7e22ce",
  "ดำเนินการ": "#4338ca",
  "รับออเดอร์แล้ว": "#1d4ed8",
  "รอส่ง": "#b45309",
  "ส่งแล้ว": "#047857",
  "เสร็จสิ้น": "#0f766e",
  "แก้ไข": "#be123c",
};

function primaryLabelStyle(label: string | null | undefined): string {
  return PRIMARY_LABEL_STYLES[label ?? ""] ?? "border-slate-200 bg-white text-slate-700";
}

function primaryLabelAnimation(label: string | null | undefined): string {
  return label === "รอแอดมิน" ? "admin-waiting-border" : "";
}

function CustomerAvatar({ conversation, className = "" }: { conversation: Conversation; className?: string }) {
  const name = conversation.customer_display_name || `ลูกค้า #${conversation.customer_id}`;
  if (!conversation.customer_profile_image_url) {
    return <span className={`inline-flex shrink-0 items-center justify-center rounded-full bg-slate-100 text-slate-400 ${className}`} aria-label={`ไม่มีรูปโปรไฟล์ของ ${name}`}><CircleUserRound className="h-[70%] w-[70%]" /></span>;
  }
  // Facebook supplies an expiring remote URL, so Next's image optimizer cannot safely cache it.
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={conversation.customer_profile_image_url} alt={`รูปโปรไฟล์ของ ${name}`} className={`shrink-0 rounded-full bg-slate-100 object-cover ${className}`} />;
}

export default function InboxPage() {
  const setMobileNavOpen = useMobileNav();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [channels, setChannels] = useState<FacebookConnection[]>([]);
  const [channelId, setChannelId] = useState<number | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [showConversationOnMobile, setShowConversationOnMobile] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [statusFilter, setStatusFilter] = useState<ConversationStatus | "">("");
  const [visibility, setVisibility] = useState<VisibilityFilter>("active");
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [drafts, setDrafts] = useState<DraftOrder[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [editingDraft, setEditingDraft] = useState<DraftOrder | null>(null);
  const [manualOrderConversationId, setManualOrderConversationId] = useState<number | null>(null);
  const [selectedItems, setSelectedItems] = useState<Record<number, number>>({});
  const [selectedItemPrices, setSelectedItemPrices] = useState<Record<number, number>>({});
  const [deliveryNote, setDeliveryNote] = useState("");
  const [replyText, setReplyText] = useState("");
  const [deliveryNoteConversationId, setDeliveryNoteConversationId] = useState<number | null>(null);
  const [addressEditorOpen, setAddressEditorOpen] = useState(false);
  const [cameraOpen, setCameraOpen] = useState(false);
  const [swipedConversationId, setSwipedConversationId] = useState<number | null>(null);
  const [cameraStream, setCameraStream] = useState<MediaStream | null>(null);
  const [capturedPhoto, setCapturedPhoto] = useState<Blob | null>(null);
  const [photoPreviewUrl, setPhotoPreviewUrl] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const photoPickerRef = useRef<HTMLInputElement>(null);
  const selectedIdRef = useRef<number | null>(null);
  const swipeStartX = useRef<number | null>(null);
  const swipeWasGesture = useRef(false);
  const selectedConversation = conversations.find((conversation) => conversation.id === selectedId) ?? null;
  const pendingDraft = selectedId === null ? null : drafts.find((draft) => draft.conversation_id === selectedId) ?? null;
  const pendingDraftAcknowledgementId = useMemo(() => {
    if (!pendingDraft) return null;
    return [...messages]
      .reverse()
      .find((message) => message.direction === "out" && message.text.trim() === ORDER_REVIEW_ACKNOWLEDGEMENT)?.id ?? null;
  }, [messages, pendingDraft]);
  const currentDeliveryNote = deliveryNoteConversationId === selectedId ? deliveryNote : selectedConversation?.delivery_note ?? "";

  function formatThaiOrderTime(timestamp: string) {
    return new Intl.DateTimeFormat("th-TH", { hour: "2-digit", minute: "2-digit" }).format(new Date(timestamp)) + " น.";
  }

  const loadConversations = useCallback(async () => {
    try {
      setError(null);
      const data = await api.listConversations({
        status: statusFilter || undefined,
        visibility,
        channelId: channelId ?? undefined,
      });
      setConversations(data);
      setSelectedId((current) => (data.some((conversation) => conversation.id === current) ? current : data[0]?.id ?? null));
    } catch (e) {
      setError(String(e));
    }
  }, [channelId, statusFilter, visibility]);

  useEffect(() => {
    void api.listFacebookConnections().then((items) => {
      setChannels(items);
      setChannelId((current) => current && items.some((item) => item.id === current) ? current : items[0]?.id ?? null);
    }).catch((err) => setError(String(err)));
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => void loadConversations(), 0);
    return () => window.clearTimeout(timer);
  }, [loadConversations]);

  const loadConversationContent = useCallback(async (conversationId: number) => {
    try {
      const [loadedMessages, loadedDrafts] = await Promise.all([
        api.listMessages(conversationId),
        api.listDraftOrders("pending"),
      ]);
      setMessages([...loadedMessages].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()));
      setDrafts(loadedDrafts);
      const readConversation = await api.markConversationRead(conversationId);
      setConversations((current) => current.map((conversation) => (conversation.id === readConversation.id ? readConversation : conversation)));
    } catch (e) {
      setError(String(e));
    }
  }, []);

  useEffect(() => {
    if (selectedId === null) {
      return;
    }
    const timer = window.setTimeout(() => void loadConversationContent(selectedId), 0);
    return () => window.clearTimeout(timer);
  }, [loadConversationContent, selectedId]);

  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  // A Facebook webhook commits the message to the database, then sends this
  // complete payload through SSE.  This avoids repeated Inbox polling while
  // retaining the database as the source of truth after a page reload.
  useEffect(() => {
    const source = new EventSource(api.inboxEventsUrl(), { withCredentials: true });
    const receiveMessage = (event: MessageEvent<string>) => {
      let incoming: InboxMessageEvent;
      try {
        incoming = JSON.parse(event.data) as InboxMessageEvent;
      } catch {
        return;
      }
      const conversation = incoming.conversation;
      if (channelId !== null && conversation.channel_id !== channelId) return;
      const matchesStatus = !statusFilter || conversation.status === statusFilter;
      const matchesVisibility =
        visibility === "all" || (visibility === "active" ? !conversation.is_hidden : conversation.is_hidden);

      setConversations((current) => {
        const withoutCurrent = current.filter((item) => item.id !== conversation.id);
        const next = matchesStatus && matchesVisibility ? [conversation, ...withoutCurrent] : withoutCurrent;
        return next.sort((left, right) =>
          Number(right.is_pinned) - Number(left.is_pinned)
          || new Date(right.last_message_at).getTime() - new Date(left.last_message_at).getTime(),
        );
      });

      const activeId = selectedIdRef.current;
      if (activeId === null) setSelectedId(conversation.id);
      if (activeId === null || activeId === conversation.id) {
        setMessages((current) =>
          [...current.filter((item) => item.id !== incoming.message.id), incoming.message].sort(
            (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
          ),
        );
      }
      if (activeId === conversation.id) {
        void api.markConversationRead(conversation.id).then((readConversation) => {
          setConversations((current) => current.map((item) => (item.id === readConversation.id ? readConversation : item)));
        }).catch(() => {
          // A future Inbox refresh will retry; never interrupt the staff view
          // merely because an alert marker could not be cleared.
        });
      }
      if (incoming.draft_order) {
        setDrafts((current) => [
          incoming.draft_order as DraftOrder,
          ...current.filter((item) => item.id !== incoming.draft_order?.id),
        ]);
      }
    };
    source.addEventListener("inbox.message", receiveMessage);
    return () => {
      source.removeEventListener("inbox.message", receiveMessage);
      source.close();
    };
  }, [channelId, statusFilter, visibility]);

  async function refreshInbox() {
    setRefreshing(true);
    try {
      await loadConversations();
      if (selectedId !== null) await loadConversationContent(selectedId);
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    if (cameraOpen && cameraStream && videoRef.current) {
      videoRef.current.srcObject = cameraStream;
      void videoRef.current.play().catch(() => setError("ไม่สามารถเปิดภาพจากกล้องได้"));
    }
  }, [cameraOpen, cameraStream]);

  const filteredConversations = useMemo(() => {
    const keyword = search.trim().toLocaleLowerCase();
    if (!keyword) return conversations;
    return conversations.filter((conversation) =>
      (conversation.customer_display_name || `ลูกค้า #${conversation.customer_id}`).toLocaleLowerCase().includes(keyword),
    );
  }, [conversations, search]);

  async function updateConversation(id: number, update: Partial<Pick<Conversation, "status" | "is_hidden" | "is_pinned" | "primary_label" | "payment_label" | "delivery_note">>): Promise<Conversation | null> {
    try {
      setUpdating(true);
      setError(null);
      const saved = await api.updateConversation(id, update);
      setConversations((current) => current.map((conversation) => (conversation.id === id ? saved : conversation)));
      await loadConversations();
      return saved;
    } catch (e) {
      setError(String(e));
      return null;
    } finally {
      setUpdating(false);
    }
  }

  async function closeConversationView(id: number, update: Partial<Pick<Conversation, "status" | "is_hidden" | "is_pinned" | "primary_label" | "payment_label" | "delivery_note">>) {
    const saved = await updateConversation(id, update);
    if (saved && selectedId === id) {
      setMessages([]);
      setDrafts([]);
      setSelectedId(null);
      setShowConversationOnMobile(false);
    }
  }

  async function toggleConversationVisibility(conversation: Conversation) {
    if (!conversation.is_hidden && !window.confirm(`ซ่อนแชตของ ${conversation.customer_display_name || `ลูกค้า #${conversation.customer_id}`} ใช่หรือไม่?`)) return;
    await closeConversationView(conversation.id, { is_hidden: !conversation.is_hidden });
  }

  async function updatePrimaryLabel(primary_label: string) {
    if (!selectedConversation) return;
    if (primary_label === "เสร็จสิ้น") {
      await closeConversationView(selectedConversation.id, { primary_label });
      return;
    }
    await updateConversation(selectedConversation.id, { primary_label });
  }

  async function updateSwipedConversationLabel(conversation: Conversation, primary_label: string) {
    if (primary_label === "เสร็จสิ้น") await closeConversationView(conversation.id, { primary_label });
    else await updateConversation(conversation.id, { primary_label });
    setSwipedConversationId(null);
  }

  function handleConversationSwipeEnd(conversationId: number, endX: number) {
    if (swipeStartX.current === null) return;
    const distance = endX - swipeStartX.current;
    if (distance < -48) {
      swipeWasGesture.current = true;
      setSwipedConversationId(conversationId);
    }
    if (distance > 24) {
      swipeWasGesture.current = true;
      setSwipedConversationId(null);
    }
    swipeStartX.current = null;
  }

  async function saveDeliveryNote() {
    if (!selectedConversation) return null;
    return updateConversation(selectedConversation.id, { delivery_note: currentDeliveryNote });
  }

  function openAddressEditor() {
    if (!selectedConversation) return;
    setDeliveryNoteConversationId(selectedConversation.id);
    setDeliveryNote(selectedConversation.delivery_note ?? "");
    setAddressEditorOpen(true);
  }

  async function saveAddressEditor() {
    const saved = await saveDeliveryNote();
    if (saved) setAddressEditorOpen(false);
  }

  async function sendDelivery() {
    if (!selectedConversation) return;
    try {
      setUpdating(true);
      setError(null);
      if (currentDeliveryNote.trim() !== (selectedConversation.delivery_note ?? "")) {
        const saved = await api.updateConversation(selectedConversation.id, { delivery_note: currentDeliveryNote });
        setConversations((current) => current.map((conversation) => (conversation.id === saved.id ? saved : conversation)));
      }
      const saved = await api.sendDelivery(selectedConversation.id);
      setConversations((current) => current.map((conversation) => (conversation.id === saved.id ? saved : conversation)));
      setMessages(await api.listMessages(selectedConversation.id));
      await loadConversations();
    } catch (e) {
      setError(String(e));
    } finally {
      setUpdating(false);
    }
  }

  function openPhotoOptionsForConversation(conversationId: number) {
    setSelectedId(conversationId);
    setError(null);
    setCameraOpen(true);
  }

  async function startCamera() {
    try {
      setError(null);
      if (!navigator.mediaDevices?.getUserMedia) {
        return;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      setCameraStream(stream);
      setCameraOpen(true);
    } catch {
      // A declined camera permission is normal. Keep the picker open so the user can choose an existing image instead.
    }
  }

  function clearCapturedPhoto() {
    if (photoPreviewUrl) URL.revokeObjectURL(photoPreviewUrl);
    setPhotoPreviewUrl(null);
    setCapturedPhoto(null);
  }

  function closeCamera() {
    cameraStream?.getTracks().forEach((track) => track.stop());
    setCameraStream(null);
    clearCapturedPhoto();
    if (photoPickerRef.current) photoPickerRef.current.value = "";
    setCameraOpen(false);
  }

  function capturePhoto() {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || !video.videoWidth || !video.videoHeight) {
      setError("กล้องยังไม่พร้อมถ่ายรูป");
      return;
    }
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")?.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob((photo) => {
      if (!photo) {
        setError("ไม่สามารถสร้างรูปจากกล้องได้");
        return;
      }
      clearCapturedPhoto();
      setCapturedPhoto(photo);
      setPhotoPreviewUrl(URL.createObjectURL(photo));
    }, "image/jpeg", 0.88);
  }

  function selectExistingPhoto() {
    photoPickerRef.current?.click();
  }

  function retakePhoto() {
    clearCapturedPhoto();
    if (!cameraStream) void startCamera();
  }

  function useExistingPhoto(event: React.ChangeEvent<HTMLInputElement>) {
    const photo = event.target.files?.[0];
    if (!photo) return;
    if (!new Set(["image/jpeg", "image/png", "image/webp"]).has(photo.type) || photo.size > 5 * 1024 * 1024) {
      setError("เลือกรูป JPG, PNG หรือ WEBP ขนาดไม่เกิน 5 MB");
      event.target.value = "";
      return;
    }
    clearCapturedPhoto();
    setCapturedPhoto(photo);
    setPhotoPreviewUrl(URL.createObjectURL(photo));
  }

  async function sendCapturedPhoto() {
    if (!selectedConversation || !capturedPhoto) return;
    try {
      setUpdating(true);
      setError(null);
      const saved = await api.sendConversationPhoto(selectedConversation.id, capturedPhoto);
      setConversations((current) => current.map((conversation) => (conversation.id === saved.id ? saved : conversation)));
      setMessages(await api.listMessages(selectedConversation.id));
      closeCamera();
      await loadConversations();
    } catch (e) {
      setError(String(e));
    } finally {
      setUpdating(false);
    }
  }

  async function confirmDraft(draft: DraftOrder) {
    try {
      setUpdating(true);
      setError(null);
      await api.confirmDraftOrder(draft.id);
      setDrafts((current) => current.filter((item) => item.id !== draft.id));
      if (selectedId !== null) setMessages(await api.listMessages(selectedId));
      await loadConversations();
    } catch (e) {
      setError(String(e));
    } finally {
      setUpdating(false);
    }
  }

  async function sendReply() {
    if (!selectedConversation || !replyText.trim()) return;
    try {
      setUpdating(true);
      setError(null);
      const sent = await api.sendConversationMessage(selectedConversation.id, replyText.trim());
      setConversations((current) => current.map((conversation) => (conversation.id === sent.conversation.id ? sent.conversation : conversation)));
      setMessages((current) => [...current, sent.message].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime()));
      setReplyText("");
    } catch (e) {
      setError(String(e));
    } finally {
      setUpdating(false);
    }
  }

  async function openEditDraft(draft: DraftOrder) {
    try {
      setError(null);
      const loadedProducts = await api.listProducts();
      setProducts(loadedProducts);
      setSelectedItems(Object.fromEntries(draft.items.filter((item) => item.product_id !== null).map((item) => [item.product_id as number, item.quantity])));
      setSelectedItemPrices(Object.fromEntries(draft.items.filter((item) => item.product_id !== null).map((item) => [item.product_id as number, item.unit_price])));
      setEditingDraft(draft);
    } catch (e) {
      setError(String(e));
    }
  }

  async function openManualOrder() {
    if (!selectedConversation) return;
    if (pendingDraft) {
      await openEditDraft(pendingDraft);
      return;
    }
    try {
      setError(null);
      setProducts(await api.listProducts());
      setSelectedItems({});
      setSelectedItemPrices({});
      setManualOrderConversationId(selectedConversation.id);
    } catch (e) {
      setError(String(e));
    }
  }

  function closeOrderEditor() {
    setEditingDraft(null);
    setManualOrderConversationId(null);
    setSelectedItemPrices({});
  }

  async function rejectDraft(draft: DraftOrder) {
    try {
      setUpdating(true);
      setError(null);
      await api.rejectDraftOrder(draft.id);
      setDrafts((current) => current.filter((item) => item.id !== draft.id));
    } catch (e) {
      setError(String(e));
    } finally {
      setUpdating(false);
    }
  }

  function setProductSelection(productId: number, selected: boolean) {
    setSelectedItems((current) => {
      const next = { ...current };
      if (selected) next[productId] = next[productId] || 1;
      else delete next[productId];
      return next;
    });
    if (selected) {
      const defaultPrice = products.find((product) => product.id === productId)?.price;
      if (defaultPrice !== undefined) setSelectedItemPrices((current) => ({ ...current, [productId]: current[productId] ?? defaultPrice }));
    } else {
      setSelectedItemPrices((current) => {
        const next = { ...current };
        delete next[productId];
        return next;
      });
    }
  }

  async function saveEditedDraft() {
    if (!editingDraft && manualOrderConversationId === null) return;
    const items = Object.entries(selectedItems)
      .filter(([, quantity]) => quantity > 0)
      .map(([productId, quantity]) => ({ product_id: Number(productId), quantity, unit_price: selectedItemPrices[Number(productId)] }));
    if (items.length === 0) {
      setError("กรุณาเลือกอย่างน้อย 1 รายการ");
      return;
    }
    try {
      setUpdating(true);
      setError(null);
      if (editingDraft) {
        const saved = await api.updateDraftOrder(editingDraft.id, { items });
        setDrafts((current) => current.map((draft) => (draft.id === saved.id ? saved : draft)));
      } else {
        const created = await api.createManualDraftOrder({ conversation_id: manualOrderConversationId as number, items });
        await api.confirmDraftOrder(created.id);
        setDrafts((current) => current.filter((draft) => draft.id !== created.id));
        if (selectedId !== null) setMessages(await api.listMessages(selectedId));
        await loadConversations();
      }
      closeOrderEditor();
    } catch (e) {
      setError(String(e));
    } finally {
      setUpdating(false);
    }
  }

  return (
    <main className="flex h-[100dvh] max-h-[100dvh] min-h-0 overflow-hidden text-sm bg-white">
      <aside className={`${showConversationOnMobile ? "hidden" : "flex"} w-full md:flex md:w-80 shrink-0 flex-col border-r overflow-y-auto`}>
        <div className="border-b p-4 space-y-3">
          <h1 className="flex items-center gap-2 text-base font-semibold">
            <button onClick={() => setMobileNavOpen(true)} className="inline-flex h-10 w-10 items-center justify-center rounded-lg bg-slate-900 text-white shadow-sm md:hidden" aria-label="เปิดเมนู"><Menu className="h-5 w-5" /></button>
            <InboxIcon className="w-4 h-4 text-amber-500" />
            Inbox
            <button
              onClick={() => void refreshInbox()}
              disabled={refreshing}
              title="ดึงข้อความล่าสุดจากระบบ"
              aria-label="ดึงข้อความล่าสุดจากระบบ"
              className="ml-auto rounded p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 disabled:cursor-not-allowed"
            >
              <RefreshCw className={`h-4 w-4 ${refreshing ? "animate-spin" : ""}`} />
            </button>
          </h1>
          <select
            aria-label="เลือก Facebook Page"
            value={channelId ?? ""}
            onChange={(event) => setChannelId(event.target.value ? Number(event.target.value) : null)}
            className="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-sm outline-none focus:border-amber-400"
            disabled={!channels.length}
          >
            {channels.length === 0 ? <option value="">ยังไม่มีเพจที่เข้าถึงได้</option> : channels.map((channel) => <option key={channel.id} value={channel.id}>{channel.name || `Facebook Page ${channel.page_id}`}</option>)}
          </select>
          <label className="relative block">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="ค้นหาชื่อลูกค้า"
              className="w-full rounded-lg border border-gray-200 py-2 pl-9 pr-3 outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-100"
            />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <select
              aria-label="กรองตามสถานะ"
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value as ConversationStatus | "")}
              className="min-w-0 rounded-lg border border-gray-200 bg-white px-2 py-2 text-xs outline-none focus:border-amber-400"
            >
              <option value="">ทุกสถานะ</option>
              {STATUS_OPTIONS.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
            <select
              aria-label="กรองการแสดงแชท"
              value={visibility}
              onChange={(event) => setVisibility(event.target.value as VisibilityFilter)}
              className="min-w-0 rounded-lg border border-gray-200 bg-white px-2 py-2 text-xs outline-none focus:border-amber-400"
            >
              <option value="active">แชทที่แสดง</option>
              <option value="hidden">แชทที่ซ่อน</option>
              <option value="all">ทั้งหมด</option>
            </select>
          </div>
        </div>

        {error && <p className="p-4 text-red-600">{error}</p>}
        <ul>
          {filteredConversations.map((conversation) => {
            return (
              <li key={conversation.id} className="relative overflow-hidden border-b">
                <div
                  className="absolute inset-0 flex bg-violet-600"
                  onTouchStart={(event) => { swipeStartX.current = event.touches[0]?.clientX ?? null; swipeWasGesture.current = false; }}
                  onTouchEnd={(event) => handleConversationSwipeEnd(conversation.id, event.changedTouches[0]?.clientX ?? 0)}
                >
                  <button
                    type="button"
                    onClick={() => {
                      if (swipeWasGesture.current) {
                        swipeWasGesture.current = false;
                        return;
                      }
                      void updateConversation(conversation.id, { is_pinned: !conversation.is_pinned }).then(() => setSwipedConversationId(null));
                    }}
                    disabled={updating}
                    className={`flex w-1/4 flex-col items-center justify-center gap-1 text-[11px] font-medium text-white disabled:cursor-not-allowed ${conversation.is_pinned ? "bg-slate-600" : "bg-amber-500"}`}
                  >
                    {conversation.is_pinned ? <PinOff className="h-5 w-5" /> : <Pin className="h-5 w-5" />}
                    {conversation.is_pinned ? "เลิกปักหมุด" : "ปักหมุด"}
                  </button>
                  <div className="flex flex-1 items-center gap-2 px-3 text-[10px] font-medium text-white">
                    <label className="min-w-0 flex-1">
                      ป้ายงาน
                      <select
                        aria-label={`เปลี่ยนป้ายงานของ ${conversation.customer_display_name || `ลูกค้า #${conversation.customer_id}`}`}
                        value={conversation.primary_label ?? ""}
                        disabled={updating}
                        onChange={(event) => void updateSwipedConversationLabel(conversation, event.target.value)}
                        className="mt-1 h-7 w-full rounded border-0 bg-white px-1 text-[11px] text-violet-800 outline-none disabled:cursor-not-allowed"
                      >
                        <option value="" disabled>เลือกป้าย</option>
                        {PRIMARY_LABEL_OPTIONS.map((label) => <option key={label} value={label}>{label}</option>)}
                      </select>
                    </label>
                    <label className="min-w-0 flex-1">
                      ป้ายการจ่ายเงิน
                      <select
                        aria-label={`เปลี่ยนป้ายการจ่ายเงินของ ${conversation.customer_display_name || `ลูกค้า #${conversation.customer_id}`}`}
                        value={conversation.payment_label ?? ""}
                        disabled={updating}
                        onChange={(event) => void updateConversation(conversation.id, { payment_label: event.target.value || null }).then(() => setSwipedConversationId(null))}
                        className="mt-1 h-7 w-full rounded border-0 bg-white px-1 text-[11px] text-violet-800 outline-none disabled:cursor-not-allowed"
                      >
                        <option value="">ไม่ระบุ</option>
                        {PAYMENT_LABEL_OPTIONS.map((label) => <option key={label} value={label}>{label}</option>)}
                      </select>
                    </label>
                  </div>
                </div>
                <div
                  className={`group relative flex items-center bg-white transition-transform duration-200 ${selectedId === conversation.id ? "bg-amber-100" : "hover:bg-amber-50"}`}
                  style={{ transform: swipedConversationId === conversation.id ? "translateX(-100%)" : "translateX(0)" }}
                  onTouchStart={(event) => { swipeStartX.current = event.touches[0]?.clientX ?? null; swipeWasGesture.current = false; }}
                  onTouchEnd={(event) => handleConversationSwipeEnd(conversation.id, event.changedTouches[0]?.clientX ?? 0)}
                >
                  <button
                    onClick={() => {
                      if (swipeWasGesture.current || swipedConversationId === conversation.id) {
                        swipeWasGesture.current = false;
                        setSwipedConversationId(null);
                        return;
                      }
                      setSelectedId(conversation.id);
                      setShowConversationOnMobile(true);
                    }}
                    className="min-w-0 flex-1 px-4 py-1.5 text-left"
                  >
                    <div className={`flex min-w-0 items-center gap-3 ${conversation.unread_count > 0 ? "font-semibold" : "font-medium"}`}>
                      <CustomerAvatar conversation={conversation} className="h-11 w-11" />
                      <div className="min-w-0 flex-1">
                        <div className="flex min-w-0 items-center gap-1.5">
                          <span className="truncate">{conversation.customer_display_name || `ลูกค้า #${conversation.customer_id}`}</span>
                          {conversation.delivery_note && <span className="inline-flex min-w-0 flex-1 items-center gap-1 text-xs font-normal text-slate-500"><MapPin className="h-3.5 w-3.5 shrink-0 text-sky-600" /><span className="truncate">{conversation.delivery_note}</span></span>}
                          {conversation.unread_count > 0 && <span title={`ข้อความลูกค้าใหม่ ${conversation.unread_count} ข้อความ`} aria-label={`ข้อความลูกค้าใหม่ ${conversation.unread_count} ข้อความ`} className="h-2.5 w-2.5 shrink-0 rounded-full bg-rose-500" />}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-1.5">
                          {conversation.primary_label && <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium ${primaryLabelStyle(conversation.primary_label)} ${primaryLabelAnimation(conversation.primary_label)}`}>{conversation.primary_label}</span>}
                          {conversation.payment_label && <span className="inline-flex rounded-full bg-sky-100 px-2 py-0.5 text-[11px] font-medium text-sky-800">{conversation.payment_label}</span>}
                          {conversation.bill_count > 0 && <span className="inline-flex shrink-0 rounded-full bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800">บิล x{conversation.bill_count}</span>}
                        </div>
                      </div>
                    </div>
                  </button>
                  <div className="mr-2 flex shrink-0 items-center gap-1">
                    <div className="flex flex-col items-center gap-0.5">
                      <button
                        onClick={() => void toggleConversationVisibility(conversation)}
                        disabled={updating}
                        title={conversation.is_hidden ? "แสดงแชท" : "ซ่อนแชท"}
                        aria-label={conversation.is_hidden ? "แสดงแชท" : "ซ่อนแชท"}
                        className="rounded-md p-1.5 text-gray-400 transition hover:bg-white hover:text-gray-700 disabled:cursor-not-allowed"
                      >
                        {conversation.is_hidden ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
                      </button>
                      {conversation.order_confirmed_at && <span className="whitespace-nowrap text-xs font-medium text-gray-500">{formatThaiOrderTime(conversation.order_confirmed_at)}</span>}
                    </div>
                    <button
                      onClick={() => openPhotoOptionsForConversation(conversation.id)}
                      disabled={updating}
                      title="ถ่ายหรือเลือกรูปเพื่อส่งให้ลูกค้า"
                      aria-label="ถ่ายหรือเลือกรูปเพื่อส่งให้ลูกค้า"
                      className="flex min-h-11 min-w-11 items-center justify-center rounded-lg bg-sky-50 text-sky-600 hover:bg-sky-100 hover:text-sky-800 disabled:cursor-not-allowed disabled:text-slate-300"
                    >
                      <Camera className="h-6 w-6" />
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
          {filteredConversations.length === 0 && !error && (
            <li className="p-4 text-gray-500">{search ? "ไม่พบแชทที่ค้นหา" : "ไม่มีแชทตามตัวกรองนี้"}</li>
          )}
        </ul>
      </aside>

      <section className={`${showConversationOnMobile ? "flex" : "hidden"} md:flex min-h-0 min-w-0 flex-1 flex-col`}>
        {selectedConversation && (
          <header className="sticky top-0 z-20 border-b border-slate-200 bg-white/95 px-3 py-2 shadow-sm backdrop-blur md:static md:mx-2 md:mb-2 md:mt-0 md:rounded-lg md:border md:border-sky-200 md:shadow-md md:shadow-slate-200/70">
            <div className="grid min-h-11 grid-cols-[2.75rem_2.75rem_minmax(0,1fr)_auto] items-center gap-1 md:flex">
              <button onClick={() => setMobileNavOpen(true)} className="inline-flex h-11 w-11 items-center justify-center rounded-lg bg-slate-900 text-white shadow-sm md:hidden" aria-label="เปิดเมนู"><Menu className="h-5 w-5" /></button>
              <button onClick={() => setShowConversationOnMobile(false)} className="inline-flex h-11 w-11 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 md:hidden" aria-label="กลับไปยังรายการแชท"><ArrowLeft className="h-5 w-5" /></button>
              <div className="min-w-0 md:flex-1">
                <div className="flex min-w-0 items-center gap-1.5 font-semibold"><span className="max-w-[46%] shrink truncate text-lg sm:max-w-[52%]">{selectedConversation.customer_display_name || `ลูกค้า #${selectedConversation.customer_id}`}</span><button type="button" onClick={openAddressEditor} className="inline-flex min-w-0 flex-1 items-center gap-1 truncate text-xs font-medium text-slate-500 hover:text-sky-700" aria-label={selectedConversation.delivery_note ? `แก้ไขที่อยู่จัดส่ง: ${selectedConversation.delivery_note}` : "เพิ่มที่อยู่จัดส่ง"}><MapPin className="h-3.5 w-3.5 shrink-0" /><span className="truncate">{selectedConversation.delivery_note || "เพิ่มที่อยู่จัดส่ง"}</span></button></div>
                <div className="hidden items-center gap-1 text-xs text-slate-400 md:flex"><Tag className="h-3.5 w-3.5" />บทสนทนา #{selectedConversation.id}</div>
              </div>
              <span className="flex shrink-0 items-center gap-1"><button onClick={() => void sendDelivery()} disabled={updating || !currentDeliveryNote.trim()} className="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg bg-sky-600 px-3 text-xs font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300" aria-label="เริ่มจัดส่ง"><Send className="h-4 w-4" /><span className="hidden sm:inline">เริ่ม</span></button></span>
            </div>
            <div className="mt-2 flex items-center gap-2 overflow-x-auto pb-0.5 md:mt-2 md:overflow-visible">
              <select
                aria-label="ป้ายงาน"
                value={selectedConversation.primary_label ?? ""}
                disabled={updating}
                onChange={(event) => {
                  const primary_label = event.target.value;
                  void updatePrimaryLabel(primary_label);
                }}
                className={`h-8 shrink-0 rounded-lg border px-2.5 text-xs font-medium outline-none disabled:cursor-not-allowed ${primaryLabelStyle(selectedConversation.primary_label)} ${primaryLabelAnimation(selectedConversation.primary_label)}`}
              >
                <option value="" disabled>เลือกป้ายงาน</option>
                {PRIMARY_LABEL_OPTIONS.map((label) => <option key={label} value={label} style={{ color: PRIMARY_LABEL_COLORS[label] }}>{label}</option>)}
              </select>
              <select
                aria-label="ป้ายการจ่ายเงิน"
                value={selectedConversation.payment_label ?? ""}
                disabled={updating}
                onChange={(event) => void updateConversation(selectedConversation.id, { payment_label: event.target.value || null })}
                className="h-8 shrink-0 rounded-lg border border-slate-200 bg-white px-2.5 text-xs font-medium text-slate-700 outline-none focus:border-sky-400 disabled:cursor-not-allowed"
              >
                <option value="">ป้ายการจ่ายเงิน</option>
                {PAYMENT_LABEL_OPTIONS.map((label) => <option key={label} value={label}>{label}</option>)}
              </select>
              <button onClick={() => void openManualOrder()} disabled={updating} className="inline-flex h-8 shrink-0 items-center rounded-lg border border-amber-300 bg-amber-50 px-2.5 text-xs font-medium text-amber-900 hover:bg-amber-100 disabled:cursor-not-allowed">คีย์ออเดอร์</button>
              <button onClick={() => void toggleConversationVisibility(selectedConversation)} disabled={updating} title={selectedConversation.is_hidden ? "แสดงแชท" : "ซ่อนแชท"} className="inline-flex h-8 shrink-0 items-center gap-1 rounded-lg border border-slate-200 px-2.5 text-xs font-medium text-slate-600 hover:bg-slate-50 disabled:cursor-not-allowed" aria-label={selectedConversation.is_hidden ? "แสดงแชท" : "ซ่อนแชท"}>{selectedConversation.is_hidden ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />}<span>{selectedConversation.is_hidden ? "แสดง" : "ซ่อน"}</span></button>
            </div>
          </header>
        )}
        {selectedConversation ? <div className="min-h-0 flex flex-1 flex-col">
          <div className="flex min-h-0 flex-1 flex-col-reverse gap-2 overflow-y-auto p-4">
            {[...messages].reverse().map((message) => {
              const showDraftReview = pendingDraft !== null && message.id === pendingDraftAcknowledgementId;
              return (
                <div key={message.id} className={`flex w-full ${message.direction === "out" ? "justify-end" : "justify-start"}`}>
                  <div className="w-fit max-w-[85%] md:max-w-md">
                    <div className={`w-full rounded-lg p-3 ${message.direction === "in" ? "bg-gray-100" : "bg-amber-100"}`}>
                      <div>{message.text}</div>
                      <div className="mt-1 text-xs text-gray-400">
                        {message.sent_by_display_name ? `ส่งโดย ${message.sent_by_display_name} · ` : ""}
                        {new Date(message.created_at).toLocaleString()}
                      </div>
                    </div>
                    {showDraftReview && pendingDraft && (
                      <div className="mt-2 w-full rounded-lg border border-amber-200 bg-amber-50 p-3 text-amber-950 shadow-sm">
                        <div className="font-semibold">รวม {pendingDraft.total.toFixed(2)} บาท</div>
                        <div className="mt-1 text-xs">{pendingDraft.items.map((item) => `${item.product_name || item.matched_text} × ${item.quantity}`).join(", ")}</div>
                        <div className="mt-3 flex gap-2">
                          <button onClick={() => void confirmDraft(pendingDraft)} disabled={updating} className="rounded bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed">ยืนยัน</button>
                          <button onClick={() => void openEditDraft(pendingDraft)} disabled={updating} className="rounded border border-amber-300 bg-white px-3 py-1.5 text-xs font-medium hover:bg-amber-100 disabled:cursor-not-allowed">แก้ไข</button>
                          <button onClick={() => void rejectDraft(pendingDraft)} disabled={updating} className="rounded border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:cursor-not-allowed">ยกเลิก</button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
          <form onSubmit={(event) => { event.preventDefault(); void sendReply(); }} className="border-t border-slate-200 bg-white p-3">
            {selectedConversation.primary_label === "รอแอดมิน" && <div className="mb-2 flex items-center gap-2 text-xs font-medium text-violet-700"><span className="h-2 w-2 animate-pulse rounded-full bg-violet-600" />รอแอดมินตอบกลับ</div>}
            <div className="flex items-end gap-2">
              <textarea value={replyText} onChange={(event) => setReplyText(event.target.value)} maxLength={4000} rows={1} placeholder="พิมพ์ข้อความถึงลูกค้า" className={`min-h-10 flex-1 resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-violet-400 focus:ring-2 focus:ring-violet-100 ${primaryLabelAnimation(selectedConversation.primary_label)}`} />
              <button type="submit" disabled={updating || !replyText.trim()} className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-lg bg-violet-600 px-3 text-xs font-medium text-white hover:bg-violet-700 disabled:cursor-not-allowed disabled:bg-violet-300"><Send className="h-4 w-4" />ส่ง</button>
            </div>
          </form>
        </div> : <div className="flex flex-1 items-center justify-center p-6 text-center text-gray-500">เลือกการสนทนาจากรายการ Inbox เพื่อดูข้อความ</div>}
      </section>
      {addressEditorOpen && selectedConversation && (
        <div className="fixed inset-0 z-[60] isolate flex items-center justify-center bg-slate-950/45 p-4" role="dialog" aria-modal="true" aria-label="แก้ไขที่อยู่จัดส่ง" onClick={() => setAddressEditorOpen(false)}>
          <form onSubmit={(event) => { event.preventDefault(); void saveAddressEditor(); }} className="max-h-[85dvh] w-full max-w-md overflow-y-auto rounded-2xl bg-white shadow-2xl" onClick={(event) => event.stopPropagation()}>
            <div className="p-5 pb-4"><div className="mb-3 flex items-center justify-between"><div><h2 className="font-semibold text-slate-900">จุดจัดส่ง</h2><p className="mt-1 text-xs text-slate-500">สำหรับ {selectedConversation.customer_display_name || `ลูกค้า #${selectedConversation.customer_id}`}</p></div><button type="button" onClick={() => setAddressEditorOpen(false)} className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-slate-500 hover:bg-slate-100" aria-label="ปิด"><X className="h-5 w-5" /></button></div>
            <label className="block text-sm font-medium text-slate-700">ที่อยู่จัดส่ง</label>
            <textarea value={currentDeliveryNote} onChange={(event) => { setDeliveryNoteConversationId(selectedConversation.id); setDeliveryNote(event.target.value); }} maxLength={1000} rows={3} autoFocus placeholder="เช่น 99/12 ถนนสุขุมวิท แขวง…" className="mt-2 min-h-28 w-full resize-y rounded-xl border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-100" /></div>
            <div className="sticky bottom-0 flex gap-2 border-t border-slate-200 bg-white px-5 pb-[max(1rem,env(safe-area-inset-bottom))] pt-3"><button type="button" onClick={() => setAddressEditorOpen(false)} className="h-11 flex-1 rounded-lg border border-slate-300 text-sm font-medium text-slate-700 hover:bg-slate-50">ยกเลิก</button><button type="submit" disabled={updating} className="h-11 flex-1 rounded-lg bg-sky-600 text-sm font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed disabled:bg-sky-300">บันทึกที่อยู่</button></div>
          </form>
        </div>
      )}

      {(editingDraft || manualOrderConversationId !== null) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" role="dialog" aria-modal="true" aria-label="แก้ไขออเดอร์">
          <div className="max-h-[85vh] w-full max-w-xl overflow-y-auto rounded-xl bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold">{editingDraft ? "แก้ไขรายการออเดอร์" : "คีย์ออเดอร์"}</h2>
                <p className="mt-1 text-xs text-gray-500">{editingDraft ? "ระบบเลือกสิ่งที่อ่านได้จากข้อความไว้แล้ว สามารถติ๊กเพิ่ม/เอาออก และเลือกได้หลายรายการ" : "เลือกสินค้าและจำนวน แล้วระบบจะยืนยันออเดอร์และส่งสรุปรายการให้ลูกค้าทันที"}</p>
              </div>
              <button onClick={closeOrderEditor} className="rounded p-1 text-gray-500 hover:bg-gray-100" aria-label="ปิดหน้าต่างแก้ไข"><X className="h-5 w-5" /></button>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
              {products.map((product) => {
                const quantity = selectedItems[product.id] || 0;
                return (
                  <label key={product.id} className={`relative min-w-0 overflow-hidden rounded-xl border bg-white transition ${quantity ? "border-amber-400 ring-1 ring-amber-300" : "border-gray-200 hover:border-amber-300"}`}>
                    <input type="checkbox" checked={quantity > 0} onChange={(event) => setProductSelection(product.id, event.target.checked)} className="absolute left-2 top-2 z-10 h-4 w-4 accent-amber-500" aria-label={`เลือก ${product.name}`} />
                    <div className="aspect-[4/3] bg-slate-100">
                      {product.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={resolveImageUrl(product.image_url) ?? undefined} alt={product.name} className="h-full w-full object-cover" />
                      ) : (
                        <div className="flex h-full flex-col items-center justify-center gap-1 text-slate-400"><ImageOff className="h-7 w-7" /><span className="text-[11px]">ไม่มีรูป</span></div>
                      )}
                    </div>
                    <div className={`p-2 ${quantity ? "bg-amber-50" : ""}`}>
                      <div className="truncate text-sm font-medium">{product.name}</div>
                      <div className="mt-0.5 text-xs text-gray-500">{product.price.toFixed(2)} บาท</div>
                      <div className="text-[11px] text-gray-400">{product.stock_mode === "unlimited" ? "สต๊อกไม่จำกัด" : `เหลือ ${product.stock_quantity}`}</div>
                      {quantity > 0 && <div className="mt-2 grid grid-cols-2 gap-2"><input aria-label={`จำนวน ${product.name}`} type="number" min="1" value={quantity} onChange={(event) => setSelectedItems((current) => ({ ...current, [product.id]: Math.max(1, Number(event.target.value) || 1) }))} onClick={(event) => event.stopPropagation()} className="w-full rounded border border-amber-300 bg-white px-2 py-1 text-center text-sm" /><input aria-label={`ราคา ${product.name}`} type="number" min="0" step="0.01" value={selectedItemPrices[product.id] ?? product.price} onChange={(event) => setSelectedItemPrices((current) => ({ ...current, [product.id]: Math.max(0, Number(event.target.value) || 0) }))} onClick={(event) => event.stopPropagation()} className="w-full rounded border border-amber-300 bg-white px-2 py-1 text-center text-sm" /></div>}
                    </div>
                  </label>
                );
              })}
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button onClick={closeOrderEditor} disabled={updating} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">ยกเลิก</button>
              <button onClick={() => void saveEditedDraft()} disabled={updating} className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed">{editingDraft ? "บันทึกรายการ" : "ยืนยันและส่งให้ลูกค้า"}</button>
            </div>
          </div>
        </div>
      )}
      {cameraOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" role="dialog" aria-modal="true" aria-label="ถ่ายรูปเพื่อส่งให้ลูกค้า">
          <div className="w-full max-w-2xl rounded-xl bg-white p-5 shadow-xl">
            <div className="flex items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold">ถ่ายรูปส่งให้ลูกค้า</h2>
                <p className="mt-1 text-xs text-gray-500">รูปจะส่งทันทีเมื่อกดส่งรูป และระบบจะไม่เก็บไฟล์รูปไว้</p>
              </div>
              <button onClick={closeCamera} className="rounded p-1 text-gray-500 hover:bg-gray-100" aria-label="ปิดกล้อง"><X className="h-5 w-5" /></button>
            </div>
            <input ref={photoPickerRef} type="file" accept="image/jpeg,image/png,image/webp" onChange={useExistingPhoto} className="hidden" />
            {!photoPreviewUrl && !cameraStream ? (
              <div className="mt-4 rounded-lg border border-dashed border-slate-300 bg-slate-50 px-5 py-10 text-center">
                <Camera className="mx-auto h-9 w-9 text-slate-400" />
                <p className="mt-3 text-sm text-slate-600">เลือกว่าอยากถ่ายรูปใหม่ หรือใช้รูปที่มีอยู่</p>
                <div className="mt-4 flex flex-wrap justify-center gap-2">
                  <button onClick={() => void startCamera()} className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700">ถ่ายรูปใหม่</button>
                  <button onClick={selectExistingPhoto} className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm hover:bg-slate-50">เลือกรูปที่มีอยู่</button>
                </div>
              </div>
            ) : (
              <div className="mt-4 overflow-hidden rounded-lg bg-black">
                {photoPreviewUrl ? (
                  <>
                    {/* Blob URLs are temporary, in-memory camera previews. Next's image optimizer cannot fetch or retain them. */}
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={photoPreviewUrl} alt="ตัวอย่างรูปที่จะส่ง" className="max-h-[55vh] w-full object-contain" />
                  </>
                ) : (
                  <video ref={videoRef} autoPlay playsInline muted className="max-h-[55vh] w-full object-contain" />
                )}
              </div>
            )}
            <canvas ref={canvasRef} className="hidden" />
            {(photoPreviewUrl || cameraStream) && <div className="mt-4 flex flex-wrap justify-end gap-2">
              {photoPreviewUrl ? (
                <>
                  <button onClick={retakePhoto} disabled={updating} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">ถ่ายรูปใหม่</button>
                  <button onClick={selectExistingPhoto} disabled={updating} className="rounded-lg border border-gray-300 px-4 py-2 text-sm hover:bg-gray-50">เลือกรูปอื่น</button>
                </>
              ) : (
                <button onClick={capturePhoto} disabled={!cameraStream} className="rounded-lg border border-slate-300 px-4 py-2 text-sm hover:bg-slate-50 disabled:cursor-not-allowed">ถ่ายภาพ</button>
              )}
              {photoPreviewUrl && <button onClick={() => void sendCapturedPhoto()} disabled={updating} className="inline-flex items-center gap-1.5 rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:cursor-not-allowed"><Send className="h-4 w-4" /> ส่งรูป</button>}
            </div>}
          </div>
        </div>
      )}
    </main>
  );
}
