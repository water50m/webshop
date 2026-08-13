export type AddItemAction = {
  id: string;
  type: "addItem";
  tempId: string;
  saleId: number;
  payload: { code?: string; product_id?: number; quantity?: number; modifier_ids?: number[] };
  createdAt: number;
};

export type QueuedAction = AddItemAction;

const KEY = "pos_offline_queue";

export function getQueue(): QueuedAction[] {
  if (typeof window === "undefined") return [];
  try {
    return JSON.parse(localStorage.getItem(KEY) || "[]");
  } catch {
    return [];
  }
}

function saveQueue(queue: QueuedAction[]) {
  localStorage.setItem(KEY, JSON.stringify(queue));
}

export function enqueue(action: Omit<AddItemAction, "id" | "createdAt">): AddItemAction {
  const full: AddItemAction = { ...action, id: crypto.randomUUID(), createdAt: Date.now() };
  saveQueue([...getQueue(), full]);
  return full;
}

export function dequeue(id: string) {
  saveQueue(getQueue().filter((a) => a.id !== id));
}

export function queueForSale(saleId: number): QueuedAction[] {
  return getQueue().filter((a) => a.saleId === saleId);
}
