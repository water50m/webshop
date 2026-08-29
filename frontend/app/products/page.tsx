"use client";

import { Package, ImageOff, LayoutGrid, Table as TableIcon, Plus, ChevronDown, ChevronUp, X, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, Ingredient, InventoryMode, Product, ProductModifier, RecipeItem, resolveImageUrl, ShopSettings } from "@/lib/api";
import { useAuth } from "@/lib/auth";

type ViewMode = "table" | "grid";

export default function ProductsPage() {
  const { user } = useAuth();
  const canSeeCost = user?.role === "owner" || user?.role === "manager";
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [viewMode, setViewMode] = useState<ViewMode>("grid");
  const [mobileControlsOpen, setMobileControlsOpen] = useState(false);

  const [categories, setCategories] = useState<string[]>([]);
  const [categoryFilter, setCategoryFilter] = useState("");

  const [modalOpen, setModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingStock, setEditingStock] = useState<number | null>(null);
  const [sku, setSku] = useState("");
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [price, setPrice] = useState("");
  const [costPrice, setCostPrice] = useState("");
  const [lowStockThreshold, setLowStockThreshold] = useState("5");
  const [stockMode, setStockMode] = useState<"tracked" | "unlimited">("tracked");
  const [isAvailable, setIsAvailable] = useState(true);
  const [showInMenuAnswer, setShowInMenuAnswer] = useState(true);
  const [shopSettings, setShopSettings] = useState<ShopSettings | null>(null);
  const [imageUrl, setImageUrl] = useState("");
  const [imageFile, setImageFile] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);

  const [adjustNotes, setAdjustNotes] = useState<Record<number, string>>({});
  const [adjustChanges, setAdjustChanges] = useState<Record<number, string>>({});
  const [restockingAll, setRestockingAll] = useState(false);

  const [modalAdjustChange, setModalAdjustChange] = useState("");
  const [modalAdjustNote, setModalAdjustNote] = useState("");

  const [editingModifiers, setEditingModifiers] = useState<ProductModifier[]>([]);
  const [newModifierName, setNewModifierName] = useState("");
  const [newModifierPrice, setNewModifierPrice] = useState("");

  const [inventoryMode, setInventoryMode] = useState<InventoryMode>("simple");
  const [ingredients, setIngredients] = useState<Ingredient[]>([]);
  const [recipeItems, setRecipeItems] = useState<RecipeItem[]>([]);
  const [newRecipeIngredientId, setNewRecipeIngredientId] = useState("");
  const [newRecipeQty, setNewRecipeQty] = useState("");

  function reload() {
    api.listProducts(search || undefined, false, categoryFilter || undefined).then(setProducts).catch((e) => setError(String(e)));
  }

  useEffect(() => {
    reload();
    api.listCategories().then(setCategories).catch(() => setCategories([]));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [categoryFilter]);

  useEffect(() => {
    api.getSettings().then((s) => { setInventoryMode(s.inventory_mode); setShopSettings(s); }).catch(() => {});
    api.listIngredients().then(setIngredients).catch(() => {});
  }, []);

  async function restockAllProducts() {
    if (restockingAll) return;
    setRestockingAll(true);
    try {
      const result = await api.restockAllProducts();
      setProducts((current) => current.map((product) => (
        product.stock_mode === "tracked"
          ? { ...product, stock_quantity: product.stock_quantity + result.change_per_product }
          : product
      )));
      setError(null);
    } catch (err) {
      setError(String(err));
    } finally {
      setRestockingAll(false);
    }
  }

  useEffect(() => {
    if (!canSeeCost) return;
    function handleRestockShortcut(event: KeyboardEvent) {
      const target = event.target;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement) return;
      if (!event.ctrlKey || !event.shiftKey || (event.key !== "+" && event.code !== "NumpadAdd")) return;
      event.preventDefault();
      void restockAllProducts();
    }
    window.addEventListener("keydown", handleRestockShortcut);
    return () => window.removeEventListener("keydown", handleRestockShortcut);
  });

  function resetForm() {
    setEditingId(null);
    setEditingStock(null);
    setSku("");
    setName("");
    setCategory("");
    setPrice("");
    setCostPrice("");
    setLowStockThreshold("5");
    setStockMode("tracked");
    setIsAvailable(true);
    setShowInMenuAnswer(true);
    setImageUrl("");
    setImageFile(null);
    setImagePreview(null);
    setModalAdjustChange("");
    setModalAdjustNote("");
    setEditingModifiers([]);
    setNewModifierName("");
    setNewModifierPrice("");
    setRecipeItems([]);
    setNewRecipeIngredientId("");
    setNewRecipeQty("");
  }

  function openCreateModal() {
    resetForm();
    setModalOpen(true);
  }

  function openEditModal(product: Product) {
    setEditingId(product.id);
    setEditingStock(product.stock_quantity);
    setSku(product.sku);
    setName(product.name);
    setCategory(product.category);
    setPrice(String(product.price));
    setCostPrice(product.cost_price ? String(product.cost_price) : "");
    setLowStockThreshold(String(product.low_stock_threshold));
    setStockMode(product.stock_mode);
    setIsAvailable(product.is_available);
    setShowInMenuAnswer(product.show_in_menu_answer);
    setImageUrl(product.image_url ?? "");
    setImageFile(null);
    setImagePreview(resolveImageUrl(product.image_url));
    setEditingModifiers(product.modifiers);
    setRecipeItems([]);
    setNewRecipeIngredientId("");
    setNewRecipeQty("");
    api.getProductRecipe(product.id).then(setRecipeItems).catch(() => {});
    setModalOpen(true);
  }

  async function handleAddRecipeItem() {
    if (editingId === null || !newRecipeIngredientId || !newRecipeQty) return;
    const qty = Number(newRecipeQty);
    if (Number.isNaN(qty) || qty <= 0) return;
    const ingredientId = Number(newRecipeIngredientId);
    const payload = [
      ...recipeItems
        .filter((r) => r.ingredient_id !== ingredientId)
        .map((r) => ({ ingredient_id: r.ingredient_id, quantity_per_unit: r.quantity_per_unit })),
      { ingredient_id: ingredientId, quantity_per_unit: qty },
    ];
    try {
      const updated = await api.updateProductRecipe(editingId, payload);
      setRecipeItems(updated);
      setNewRecipeIngredientId("");
      setNewRecipeQty("");
    } catch (err) {
      setError(String(err));
    }
  }

  async function handleDeleteRecipeItem(recipeItemId: number) {
    if (editingId === null) return;
    const payload = recipeItems
      .filter((r) => r.id !== recipeItemId)
      .map((r) => ({ ingredient_id: r.ingredient_id, quantity_per_unit: r.quantity_per_unit }));
    try {
      const updated = await api.updateProductRecipe(editingId, payload);
      setRecipeItems(updated);
    } catch (err) {
      setError(String(err));
    }
  }

  async function handleAddModifier() {
    if (editingId === null || !newModifierName.trim()) return;
    try {
      const updated = await api.createModifier(editingId, {
        name: newModifierName.trim(),
        price_delta: Number(newModifierPrice) || 0,
      });
      setEditingModifiers(updated.modifiers);
      setNewModifierName("");
      setNewModifierPrice("");
    } catch (err) {
      setError(String(err));
    }
  }

  async function handleDeleteModifier(modifierId: number) {
    if (editingId === null) return;
    try {
      const updated = await api.deleteModifier(editingId, modifierId);
      setEditingModifiers(updated.modifiers);
    } catch (err) {
      setError(String(err));
    }
  }

  function closeModal() {
    setModalOpen(false);
    resetForm();
  }

  function handleImageFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0] ?? null;
    setImageFile(f);
    setImagePreview(f ? URL.createObjectURL(f) : resolveImageUrl(imageUrl));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const payload = {
      sku,
      name,
      category,
      price: Number(price),
      cost_price: Number(costPrice) || 0,
      low_stock_threshold: Number(lowStockThreshold),
      stock_mode: stockMode,
      is_available: isAvailable,
      show_in_menu_answer: showInMenuAnswer,
      image_url: imageUrl || null,
    };
    try {
      const product = editingId !== null ? await api.updateProduct(editingId, payload) : await api.createProduct(payload);
      if (imageFile) {
        await api.uploadProductImage(product.id, imageFile);
      }
      setModalOpen(false);
      resetForm();
      reload();
    } catch (err) {
      setError(String(err));
    }
  }

  async function handleAdjust(productId: number) {
    const changeStr = adjustChanges[productId];
    const change = Number(changeStr);
    if (!changeStr || Number.isNaN(change) || change === 0) return;
    try {
      await api.adjustStock(productId, change, adjustNotes[productId] || "");
      setAdjustChanges((prev) => ({ ...prev, [productId]: "" }));
      setAdjustNotes((prev) => ({ ...prev, [productId]: "" }));
      reload();
    } catch (err) {
      setError(String(err));
    }
  }

  async function handleModalAdjust() {
    if (editingId === null) return;
    const change = Number(modalAdjustChange);
    if (!modalAdjustChange || Number.isNaN(change) || change === 0) return;
    try {
      const updated = await api.adjustStock(editingId, change, modalAdjustNote);
      setEditingStock(updated.stock_quantity);
      setModalAdjustChange("");
      setModalAdjustNote("");
      reload();
    } catch (err) {
      setError(String(err));
    }
  }

  async function updateMenuAnswerFormat(menu_answer_format: "text" | "image") {
    if (!shopSettings) return;
    try {
      const saved = await api.updateSettings({ ...shopSettings, menu_answer_format });
      setShopSettings(saved);
    } catch (err) {
      setError(String(err));
    }
  }

  async function toggleMenuAnswer(product: Product, show_in_menu_answer: boolean) {
    try {
      const updated = await api.updateProduct(product.id, {
        sku: product.sku,
        name: product.name,
        category: product.category,
        price: product.price,
        cost_price: product.cost_price,
        low_stock_threshold: product.low_stock_threshold,
        stock_mode: product.stock_mode,
        is_available: product.is_available,
        image_url: product.image_url,
        show_in_menu_answer,
      });
      setProducts((current) => current.map((item) => item.id === updated.id ? updated : item));
      setError(null);
    } catch (err) {
      setError(String(err));
    }
  }

  return (
    <main className="p-4 md:p-6 lg:p-8">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center justify-between gap-3">
          <h1 className="flex items-center gap-2 text-xl font-semibold">
            <Package className="h-5 w-5 text-amber-500" />
            สินค้า/สต๊อก
          </h1>
          <button
            onClick={() => setMobileControlsOpen((open) => !open)}
            aria-expanded={mobileControlsOpen}
            className="inline-flex min-h-10 min-w-10 items-center justify-center rounded-lg border border-slate-300 text-slate-700 hover:bg-slate-50 md:hidden"
          >
            {mobileControlsOpen ? <ChevronUp className="h-5 w-5" /> : <ChevronDown className="h-5 w-5" />}
          </button>
        </div>
        <div className={`${mobileControlsOpen ? "flex" : "hidden"} flex-wrap items-center gap-2 md:flex`}>
          {shopSettings && <label className="flex items-center gap-2 text-xs text-slate-600">
            ตอบ “มีอะไรบ้าง”
            <select value={shopSettings.menu_answer_format} onChange={(e) => void updateMenuAnswerFormat(e.target.value as "text" | "image")} className="rounded border border-slate-300 bg-white px-2 py-2">
              <option value="text">เป็นข้อความ</option>
              <option value="image">เป็นรูปเมนูรวม</option>
            </select>
          </label>}
          {canSeeCost && <button onClick={() => void restockAllProducts()} disabled={restockingAll} title="คีย์ลัด Ctrl + Shift + +" className="px-3 py-2 rounded border border-emerald-300 bg-emerald-50 text-emerald-800 hover:bg-emerald-100 disabled:opacity-50 transition-colors">{restockingAll ? "กำลังเพิ่ม..." : "เพิ่มสต๊อกทั้งหมด +10"}</button>}
          <button
            onClick={openCreateModal}
            className="flex items-center gap-1.5 px-4 py-2 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors"
          >
            <Plus className="w-4 h-4" />
            เพิ่มสินค้า
          </button>
        </div>
      </div>
      {error && <p className="text-red-600 mb-4">{error}</p>}

      <div className={`${mobileControlsOpen ? "flex" : "hidden"} mb-4 flex-wrap gap-2 md:flex`}>
        <input
          type="text"
          placeholder="ค้นหา sku/ชื่อสินค้า"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && reload()}
          className="border rounded px-3 py-2 flex-1 min-w-48"
        />
        <button onClick={reload} className="px-4 py-2 rounded border">
          ค้นหา
        </button>
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="border rounded px-3 py-2"
        >
          <option value="">ทุกหมวดหมู่</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <div className="flex border rounded overflow-hidden">
          <button
            onClick={() => setViewMode("table")}
            title="มุมมองตาราง"
            className={`p-1.5 transition-colors ${
              viewMode === "table" ? "bg-amber-500 text-white" : "hover:bg-gray-100"
            }`}
          >
            <TableIcon className="w-4 h-4" />
          </button>
          <button
            onClick={() => setViewMode("grid")}
            title="มุมมองรูปภาพ"
            className={`p-1.5 transition-colors ${
              viewMode === "grid" ? "bg-amber-500 text-white" : "hover:bg-gray-100"
            }`}
          >
            <LayoutGrid className="w-4 h-4" />
          </button>
        </div>
      </div>

      {viewMode === "grid" ? (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-8 gap-3">
          {products.map((product) => {
            const low = product.stock_mode === "tracked" && product.stock_quantity <= product.low_stock_threshold;
            return (
              <div
                key={product.id}
                className="group relative aspect-square rounded-xl overflow-hidden border bg-gray-50 cursor-pointer"
                onClick={() => openEditModal(product)}
              >
                {product.image_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={resolveImageUrl(product.image_url) ?? undefined}
                    alt={product.name}
                    className="absolute inset-0 w-full h-full object-cover"
                  />
                ) : (
                  <div className="absolute inset-0 flex items-center justify-center text-gray-300">
                    <ImageOff className="w-10 h-10" />
                  </div>
                )}

                {low && (
                  <span className="absolute top-2 right-2 px-1.5 py-0.5 rounded text-[10px] bg-red-600 text-white">
                    ใกล้หมด
                  </span>
                )}

                <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/20 to-transparent" />

                <div className="absolute inset-x-0 bottom-0 p-3 text-white">
                  <div className="font-semibold text-sm leading-tight">{product.name}</div>
                  <div className="text-xs text-white/70 mb-1">
                    {product.sku}
                    {product.category && ` · ${product.category}`}
                  </div>
                  {product.discounted_price !== null ? (
                    <div className="text-sm">
                      <span className="line-through text-white/50 mr-1">
                        {product.price.toLocaleString()}
                      </span>
                      <span className="text-amber-300 font-medium">
                        {product.discounted_price.toLocaleString()}
                      </span>
                    </div>
                  ) : (
                    <div className="text-sm">{product.price.toLocaleString()} บาท</div>
                  )}
                  <div className="text-xs text-white/80">{!product.is_available ? "หมด" : product.stock_mode === "unlimited" ? "สต็อกไม่จำกัด" : `คงเหลือ ${product.stock_quantity}`}</div>
                </div>
              </div>
            );
          })}
          {products.length === 0 && !error && (
            <p className="text-gray-500 col-span-full">ยังไม่มีสินค้า</p>
          )}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[720px] text-sm">
          <thead>
            <tr className="bg-gray-50 text-left">
              <th className="p-2"></th>
              <th className="p-2">SKU</th>
              <th className="p-2">ชื่อสินค้า</th>
              <th className="p-2">หมวดหมู่</th>
              <th className="p-2">ราคา</th>
                  <th className="p-2">สต๊อก</th>
                  <th className="p-2">ตอบเมนู</th>
              <th className="p-2">ปรับสต๊อก</th>
            </tr>
          </thead>
          <tbody>
            {products.map((product) => {
              const low = product.stock_mode === "tracked" && product.stock_quantity <= product.low_stock_threshold;
              return (
                <tr
                  key={product.id}
                  className={`border-t transition-colors hover:bg-amber-50 cursor-pointer ${low ? "bg-red-50" : ""}`}
                  onClick={() => openEditModal(product)}
                >
                  <td className="p-2">
                    {product.image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={resolveImageUrl(product.image_url) ?? undefined}
                        alt={product.name}
                        className="w-9 h-9 rounded object-cover border"
                      />
                    ) : (
                      <div className="w-9 h-9 rounded border flex items-center justify-center text-gray-300">
                        <ImageOff className="w-4 h-4" />
                      </div>
                    )}
                  </td>
                  <td className="p-2">{product.sku}</td>
                  <td className="p-2">{product.name}</td>
                  <td className="p-2 text-gray-500">{product.category}</td>
                  <td className="p-2">
                    {product.discounted_price !== null ? (
                      <span>
                        <span className="line-through text-gray-400 mr-1">
                          {product.price.toLocaleString()}
                        </span>
                        <span className="text-amber-600 font-medium">
                          {product.discounted_price.toLocaleString()}
                        </span>
                      </span>
                    ) : (
                      product.price.toLocaleString()
                    )}
                  </td>
                  <td className={`p-2 ${low ? "text-red-600 font-semibold" : ""}`}>
                    {!product.is_available ? "หมด" : product.stock_mode === "unlimited" ? "ไม่จำกัด" : product.stock_quantity}
                    {low && " (ใกล้หมด)"}
                  </td>
                  <td className="p-2" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={product.show_in_menu_answer}
                      onChange={(e) => void toggleMenuAnswer(product, e.target.checked)}
                      title="แสดงเมนูนี้เมื่อลูกค้าถามว่ามีอะไรบ้าง"
                      aria-label={`ตอบเมนู: ${product.name}`}
                      className="h-4 w-4 accent-amber-500"
                    />
                  </td>
                  <td className="p-2" onClick={(e) => e.stopPropagation()}>
                    <div className="flex gap-1">
                      {product.stock_mode === "tracked" ? <input
                        type="number"
                        placeholder="+/-"
                        value={adjustChanges[product.id] ?? ""}
                        onChange={(e) =>
                          setAdjustChanges((prev) => ({ ...prev, [product.id]: e.target.value }))
                        }
                        className="border rounded px-1 py-0.5 w-16"
                      /> : <span className="px-1 text-xs text-gray-500">ไม่ตัดสต็อก</span>}
                      {product.stock_mode === "tracked" && <input
                        type="text"
                        placeholder="หมายเหตุ"
                        value={adjustNotes[product.id] ?? ""}
                        onChange={(e) =>
                          setAdjustNotes((prev) => ({ ...prev, [product.id]: e.target.value }))
                        }
                        className="border rounded px-1 py-0.5 w-24"
                      />}
                      {product.stock_mode === "tracked" && <button
                        onClick={() => handleAdjust(product.id)}
                        className="px-2 py-0.5 rounded border"
                      >
                        ปรับ
                      </button>}
                    </div>
                  </td>
                </tr>
              );
            })}
            {products.length === 0 && !error && (
              <tr>
                <td colSpan={8} className="p-2 text-gray-500">
                  ยังไม่มีสินค้า
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      )}

      {modalOpen && (
        <div
          className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50"
          onClick={closeModal}
        >
          <div
            className="bg-white rounded-xl p-6 w-full max-w-md shadow-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">
                {editingId !== null ? "แก้ไขสินค้า" : "เพิ่มสินค้าใหม่"}
              </h2>
              <button onClick={closeModal} className="text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleSubmit} className="space-y-3">
              <div>
                <label className="block text-xs text-gray-500 mb-1">SKU/บาร์โค้ด</label>
                <input
                  type="text"
                  required
                  value={sku}
                  onChange={(e) => setSku(e.target.value)}
                  className="border rounded px-2 py-1.5 w-full"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">ชื่อสินค้า</label>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="border rounded px-2 py-1.5 w-full"
                />
              </div>
              <div>
                <label className="block text-xs text-gray-500 mb-1">หมวดหมู่</label>
                <input
                  type="text"
                  list="category-options"
                  value={category}
                  onChange={(e) => setCategory(e.target.value)}
                  placeholder="เช่น สลัด, เครื่องดื่ม, ของหวาน"
                  className="border rounded px-2 py-1.5 w-full"
                />
                <datalist id="category-options">
                  {categories.map((c) => (
                    <option key={c} value={c} />
                  ))}
                </datalist>
              </div>
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className="block text-xs text-gray-500 mb-1">ราคา</label>
                  <input
                    type="number"
                    step="0.01"
                    required
                    value={price}
                    onChange={(e) => setPrice(e.target.value)}
                    className="border rounded px-2 py-1.5 w-full"
                  />
                </div>
                <div className="flex-1">
                  <label className="block text-xs text-gray-500 mb-1">เตือนเมื่อเหลือ</label>
                  <input
                    type="number"
                    required
                    value={lowStockThreshold}
                    onChange={(e) => setLowStockThreshold(e.target.value)}
                    className="border rounded px-2 py-1.5 w-full"
                  />
                </div>
              </div>
              <div className="rounded-lg border border-slate-200 p-3">
                <label className="block text-xs text-gray-500 mb-1">รูปแบบสต็อก</label>
                <select
                  value={stockMode}
                  onChange={(e) => setStockMode(e.target.value as "tracked" | "unlimited")}
                  className="border rounded px-2 py-1.5 w-full"
                >
                  <option value="tracked">ตัดสต็อกตามจำนวน</option>
                  <option value="unlimited">สต็อกไม่จำกัด</option>
                </select>
                <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
                  <input type="checkbox" checked={isAvailable} onChange={(e) => setIsAvailable(e.target.checked)} />
                  พร้อมรับออเดอร์
                </label>
                <label className="mt-2 flex items-center gap-2 text-sm text-slate-700">
                  <input type="checkbox" checked={showInMenuAnswer} onChange={(e) => setShowInMenuAnswer(e.target.checked)} />
                  แสดงเมนูนี้เมื่อลูกค้าถามว่า “มีอะไรบ้าง”
                </label>
                {stockMode === "unlimited" && <p className="mt-2 text-xs text-slate-500">ระบบจะไม่ลดจำนวนสต็อก แต่ยกเลิก “พร้อมรับออเดอร์” ได้เมื่อต้องการระบุว่าหมด</p>}
              </div>
              {canSeeCost && (
                <div>
                  <label className="block text-xs text-gray-500 mb-1">ต้นทุนต่อหน่วย (ไม่บังคับ)</label>
                  <input
                    type="number"
                    step="0.01"
                    value={costPrice}
                    onChange={(e) => setCostPrice(e.target.value)}
                    className="border rounded px-2 py-1.5 w-full"
                  />
                </div>
              )}
              <div>
                <label className="block text-xs text-gray-500 mb-1">รูปภาพสินค้า (ไม่บังคับ)</label>
                <div className="flex gap-2 items-center mb-2">
                  {imagePreview ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={imagePreview} alt="" className="w-12 h-12 rounded object-cover border shrink-0" />
                  ) : (
                    <div className="w-12 h-12 rounded border flex items-center justify-center text-gray-300 shrink-0">
                      <ImageOff className="w-5 h-5" />
                    </div>
                  )}
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    onChange={handleImageFileChange}
                    className="text-xs flex-1 cursor-pointer file:cursor-pointer file:hover:bg-gray-200 file:transition-colors"
                  />
                </div>
                <input
                  type="text"
                  placeholder="หรือใส่ลิงก์รูปภาพ (URL)"
                  value={imageUrl}
                  onChange={(e) => {
                    setImageUrl(e.target.value);
                    if (!imageFile) setImagePreview(resolveImageUrl(e.target.value));
                  }}
                  className="border rounded px-2 py-1.5 w-full text-sm"
                />
              </div>

              {editingId !== null && stockMode === "tracked" && (
                <div className="border-t pt-3">
                  <label className="block text-xs text-gray-500 mb-1">
                    สต๊อกปัจจุบัน: <span className="font-semibold text-gray-700">{editingStock}</span>
                  </label>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-[7rem_minmax(0,1fr)_auto]">
                    <input
                      type="number"
                      placeholder="+/- จำนวน"
                      value={modalAdjustChange}
                      onChange={(e) => setModalAdjustChange(e.target.value)}
                      className="w-full border rounded px-2 py-1.5 sm:w-28"
                    />
                    <input
                      type="text"
                      placeholder="หมายเหตุ"
                      value={modalAdjustNote}
                      onChange={(e) => setModalAdjustNote(e.target.value)}
                      className="min-w-0 border rounded px-2 py-1.5"
                    />
                    <button
                      type="button"
                      onClick={handleModalAdjust}
                      className="col-span-2 min-h-11 whitespace-nowrap rounded border px-3 py-1.5 hover:bg-gray-50 transition-colors sm:col-span-1"
                    >
                      ปรับสต๊อก
                    </button>
                  </div>
                </div>
              )}
              {editingId !== null && stockMode === "unlimited" && (
                <div className="border-t pt-3 text-sm text-slate-600">
                  สินค้านี้เป็นสต็อกไม่จำกัด จึงไม่มีการปรับจำนวนคงเหลือ
                </div>
              )}

              {editingId !== null && (
                <div className="border-t pt-3">
                  <label className="block text-xs text-gray-500 mb-1">ตัวเลือกเสริม (ท็อปปิ้ง/ซอส)</label>
                  <div className="space-y-1 mb-2">
                    {editingModifiers.map((m) => (
                      <div key={m.id} className="flex items-center justify-between text-sm border rounded px-2 py-1">
                        <span>
                          {m.name}{" "}
                          <span className="text-gray-400">
                            ({m.price_delta >= 0 ? "+" : ""}
                            {m.price_delta})
                          </span>
                        </span>
                        <button
                          type="button"
                          onClick={() => handleDeleteModifier(m.id)}
                          className="text-red-500 hover:text-red-600"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                    {editingModifiers.length === 0 && (
                      <p className="text-xs text-gray-400">ยังไม่มีตัวเลือกเสริม</p>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-[minmax(0,1fr)_6rem_auto]">
                    <input
                      type="text"
                      placeholder="ชื่อตัวเลือก เช่น ไข่ต้ม"
                      value={newModifierName}
                      onChange={(e) => setNewModifierName(e.target.value)}
                      className="col-span-2 min-w-0 border rounded px-2 py-1.5 sm:col-span-1"
                    />
                    <input
                      type="number"
                      step="0.01"
                      placeholder="ราคาเสริม"
                      value={newModifierPrice}
                      onChange={(e) => setNewModifierPrice(e.target.value)}
                      className="w-full border rounded px-2 py-1.5 sm:w-24"
                    />
                    <button
                      type="button"
                      onClick={handleAddModifier}
                      className="min-h-11 whitespace-nowrap rounded border px-3 py-1.5 hover:bg-gray-50 transition-colors"
                    >
                      เพิ่ม
                    </button>
                  </div>
                </div>
              )}

              {editingId !== null && inventoryMode === "recipe" && (
                <div className="border-t pt-3">
                  <label className="block text-xs text-gray-500 mb-1">
                    สูตร/วัตถุดิบ (ตัดสต๊อกวัตถุดิบอัตโนมัติตอนขาย — ถ้าไม่ตั้งสูตร จะตัดสต๊อกของสินค้านี้เองตามปกติ)
                  </label>
                  <div className="space-y-1 mb-2">
                    {recipeItems.map((r) => (
                      <div key={r.id} className="flex items-center justify-between text-sm border rounded px-2 py-1">
                        <span>
                          {r.ingredient_name} <span className="text-gray-400">({r.quantity_per_unit} {r.unit}/หน่วย)</span>
                        </span>
                        <button
                          type="button"
                          onClick={() => handleDeleteRecipeItem(r.id)}
                          className="text-red-500 hover:text-red-600"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    ))}
                    {recipeItems.length === 0 && <p className="text-xs text-gray-400">ยังไม่ได้ตั้งสูตร</p>}
                  </div>
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-[minmax(0,1fr)_7rem_auto]">
                    <select
                      value={newRecipeIngredientId}
                      onChange={(e) => setNewRecipeIngredientId(e.target.value)}
                      className="col-span-2 min-w-0 border rounded px-2 py-1.5 sm:col-span-1"
                    >
                      <option value="">เลือกวัตถุดิบ</option>
                      {ingredients.map((i) => (
                        <option key={i.id} value={i.id}>
                          {i.name} ({i.unit})
                        </option>
                      ))}
                    </select>
                    <input
                      type="number"
                      step="0.01"
                      placeholder="จำนวน/หน่วย"
                      value={newRecipeQty}
                      onChange={(e) => setNewRecipeQty(e.target.value)}
                      className="w-full border rounded px-2 py-1.5 sm:w-28"
                    />
                    <button
                      type="button"
                      onClick={handleAddRecipeItem}
                      className="min-h-11 whitespace-nowrap rounded border px-3 py-1.5 hover:bg-gray-50 transition-colors"
                    >
                      เพิ่ม
                    </button>
                  </div>
                  {ingredients.length === 0 && (
                    <p className="text-xs text-gray-400 mt-1">ยังไม่มีวัตถุดิบ ไปเพิ่มได้ที่หน้า &quot;วัตถุดิบ&quot;</p>
                  )}
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <button
                  type="submit"
                  className="flex-1 px-4 py-2 rounded bg-amber-500 text-white hover:bg-amber-600 transition-colors"
                >
                  {editingId !== null ? "บันทึก" : "เพิ่มสินค้า"}
                </button>
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 rounded border hover:bg-gray-50 transition-colors"
                >
                  ยกเลิก
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </main>
  );
}
