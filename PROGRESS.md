# Progress

## Phase 1: รับ Order จาก Meta (Messenger + Instagram DM) + LINE OA

### Backend (FastAPI)
- [x] Scaffold โปรเจกต์ `backend/` (config, db, requirements, .env.example) — [backend/app/main.py](backend/app/main.py)
- [x] DB models: channels, customers, conversations, messages, products, draft_orders, draft_order_items — [backend/app/models.py](backend/app/models.py)
- [x] Webhook Meta: GET verify + POST รับข้อความ (พร้อมตรวจ signature) — [backend/app/webhooks/meta.py](backend/app/webhooks/meta.py)
- [x] Webhook LINE: POST รับข้อความ (ตรวจ `X-Line-Signature`) — [backend/app/webhooks/line.py](backend/app/webhooks/line.py)
- [x] `ChannelType.line` เพิ่มเข้า enum — [backend/app/models.py](backend/app/models.py)
- [x] Service ตีความข้อความสั่งซื้อ — [backend/app/services/order_parser.py](backend/app/services/order_parser.py):
  1. จัดประเภทข้อความ: ทักทาย/คำถาม/ออเดอร์ (ถ้าไม่ใช่ทักทาย/คำถาม → ถือเป็นออเดอร์)
  2. จับคู่คำในข้อความกับชื่อเมนู (Product), ท็อปปิ้ง (ProductModifier), วัตถุดิบ (Ingredient)
  3. เช็คคำปฏิเสธ (ไม่/ไม่ใส่/ไม่เอา/งด ฯลฯ) ในช่วง 8 ตัวอักษรก่อนหน้าคำที่ match แต่ละคำแยกกัน
  4. ใช้เฉพาะข้อความที่เพิ่งส่งเข้ามา ไม่ดึงประวัติแชทเก่ามาตีความซ้ำ
- [x] เชื่อม parser เข้า `message_ingest.py`: ข้อความทักทาย/คำถามไม่สร้าง draft order, เมนูที่ถูกปฏิเสธไม่ถูกเพิ่ม, ท็อปปิ้ง/วัตถุดิบที่ match แนบเป็น `special_request` ของรายการเมนูที่อยู่ก่อนหน้าในข้อความเดียวกัน
- [x] เพิ่มคอลัมน์ `DraftOrderItem.special_request`
- [x] REST API: conversations, draft-orders (list/get/update/confirm/reject) รวม `special_request` ในผลลัพธ์ — [backend/app/api](backend/app/api)
- [x] ทดสอบด้วย pytest (`backend/tests/test_order_parser.py`): แยกทักทาย/คำถาม/ออเดอร์, match เมนู+ท็อปปิ้ง, ตรวจคำปฏิเสธไม่ leak ข้ามคำ, webhook Meta/LINE สร้าง draft order ที่ถูกต้อง, เมนูที่ถูกปฏิเสธไม่ถูกเพิ่ม, ข้อความทักทายไม่สร้าง draft order — ผ่านทั้งหมด
- [x] เพิ่มตัวเลือก Algorithm ดิบ vs AI สำหรับตีความคำสั่งซื้อ — `OrderParserMode` enum + `ShopSettings.order_parser_mode`/`ai_api_key` — [backend/app/models.py](backend/app/models.py)
- [x] `app/services/ai_order_parser.py` — ส่ง catalog (เมนู/ท็อปปิ้ง/วัตถุดิบ) + ข้อความลูกค้าให้ Claude ตีความเป็น JSON, ปฏิเสธชื่อที่ไม่อยู่ใน catalog (กัน AI เดาชื่อเอง)
- [x] `message_ingest.resolve_order_matches` เลือก parser ตาม setting, **fallback เป็น algorithm อัตโนมัติ**ถ้าเรียก AI ไม่สำเร็จ (ไม่มี key/เน็ตล่ม/API error) แทนที่จะทิ้งข้อความ
- [x] ทดสอบด้วย pytest (`backend/tests/test_ai_order_parser.py`, 24 เคส): ตั้งค่า mode ผ่าน settings API, แปลงผลลัพธ์ AI เป็น matches ถูกต้อง (รวม quantity ทำซ้ำ match, negation), ข้าม hallucinated name, raise error ตอนไม่มี key/API ตอบ error, ingest ใช้ AI parser ตอนเลือกโหมด ai, **fallback เป็น algorithm เมื่อ AI call fail** — ผ่านทั้งหมด

### Frontend (Next.js)
- [x] Scaffold โปรเจกต์ `frontend/`
- [x] หน้า `/inbox` — ดูรายการสนทนา + ข้อความ
- [x] หน้า `/orders/draft` และ `/orders/draft/[id]` — ตรวจ/แก้ไข/ยืนยัน/ปฏิเสธ draft order พร้อมแสดง `special_request` ต่อรายการ
- [x] หน้า `/settings` — เพิ่มส่วนเลือก Algorithm ดิบ/AI พร้อมช่องกรอก AI API Key (แสดงเฉพาะตอนเลือกโหมด AI)
- [x] `npm run build` ผ่าน ไม่มี TypeScript error

### เอกสาร/setup
- [x] [README.md](README.md) — วิธีรัน backend/frontend, เปิด tunnel, ตั้งค่า Meta App + LINE OA ทีละขั้น, อธิบายข้อจำกัดของการตีความคำสั่งซื้อ

### ยังไม่ทำ
- [ ] เชื่อม Meta App / LINE OA ของจริง (สร้าง App/Channel, ผูก Page/IG/LINE OA, ตั้ง webhook URL)
- [ ] หน้าจัดการสินค้า (ตอนนี้ต้องเพิ่มผ่าน DB ตรงๆ)
- [ ] ตอบกลับลูกค้าอัตโนมัติ (รับเข้าอย่างเดียว ยังไม่ส่งออก)
- [ ] รองรับจำนวน/หน่วยนับในประโยค (เช่น "2 จาน"), คำพ้องความหมาย, negation ข้ามข้อความ — ดูหัวข้อ "ข้อจำกัดของการตีความคำสั่งซื้อ" ใน README

## Phase 2: บัญชี/ภาษี

### Backend (FastAPI)
- [x] เพิ่ม `unit_price` ใน `draft_order_items` (snapshot ราคาตอนสร้าง/แก้ไข) และ `confirmed_at` ใน `draft_orders`
- [x] โมเดล `Expense` (หมวดหมู่ enum: cost_of_goods/shipping/rent/utilities/marketing/other) และ `ShopSettings` (shop_type: individual/juristic)
- [x] `app/services/accounting.py` — คำนวณรายรับจาก confirmed draft orders, สรุปรายจ่ายแยกหมวด, ประมาณภาษีตามประเภทร้าน
- [x] REST API: `/api/expenses` (CRUD), `/api/settings` (get/update shop_type), `/api/reports/summary` (รายเดือน/รายปี)
- [x] ทดสอบ end-to-end ด้วย TestClient (webhook → confirm → unit_price/confirmed_at → expense → summary → เปลี่ยน shop_type)

### Frontend (Next.js)
- [x] หน้า `/expenses` — เพิ่ม/ลบรายจ่ายแยกหมวด
- [x] หน้า `/settings` — เลือกประเภทร้าน (บุคคลธรรมดา/นิติบุคคล)
- [x] หน้า `/reports` — สรุปรายรับ/รายจ่าย/กำไรสุทธิ/ภาษีประมาณการ รายเดือน/รายปี (พร้อม disclaimer)
- [x] หน้า draft order detail แสดงราคา/หน่วยและยอดรวมต่อรายการ
- [x] `npm run build` ผ่าน ไม่มี TypeScript error

### หมายเหตุ
- ภาษีเป็น**ประมาณการอย่างง่าย** (บุคคลธรรมดา: หักลดหย่อนส่วนตัว 60,000 บาทแล้วคิดขั้นบันได; นิติบุคคล: อัตรา SME แบบง่าย) ไม่ใช่คำแนะนำทางภาษีที่แม่นยำ 100%
- เพิ่มคอลัมน์ใหม่ในตารางเดิม (`draft_order_items.unit_price`, `draft_orders.confirmed_at`) — โปรเจกต์ยังไม่มี migration tool ต้องลบ DB dev เดิม (`dev.db`/ตาราง postgres) แล้วให้ `create_all` สร้างใหม่ตอน restart backend
- ยังไม่ทำ: ดึงยอดรายรับแบบ real-time/กราฟ, export รายงานเป็นไฟล์

## Phase 3: LINE OA Chatbot (ยังไม่เริ่ม)
- [ ] เชื่อม LINE Messaging API
- [ ] Rich menu / Flex message แสดงสินค้า
- [ ] สร้างออเดอร์เข้า pipeline เดียวกับ Meta

## Phase 4: POS + สต๊อกจริง

### Backend (FastAPI)
- [x] เพิ่ม `stock_quantity`/`low_stock_threshold` ใน `Product`, โมเดล `StockMovement` (audit trail การเข้า/ออกสต๊อกทุกช่องทาง) — [backend/app/models.py](backend/app/models.py)
- [x] โมเดล `Sale`/`SaleItem` รองรับหลายบิลพร้อมกัน (status: held/completed/voided), ส่วนลดต่อรายการ/ต่อบิล, วิธีชำระเงิน (เงินสด/โอน)
- [x] `app/services/stock.py` — ปรับสต๊อกกลาง พร้อมกันสต๊อกติดลบสำหรับ POS
- [x] `app/services/pos.py` — สร้าง/แก้ไขบิล, คำนวณยอด, checkout (ตัดสต๊อก+คำนวณเงินทอน), void (คืนสต๊อก)
- [x] REST API: `/api/products` (list/search/lookup ด้วย sku, create/update, ปรับสต๊อก), `/api/pos/sales` (CRUD บิล/รายการ, checkout, void)
- [x] เชื่อมสต๊อกพูลเดียวกับ Phase 1: ยืนยัน draft order จาก Meta/LINE ก็ตัดสต๊อกด้วย (`draft_orders.py` confirm)
- [x] `accounting.py` รวมยอดขายจาก POS เข้ารายรับในรายงานด้วย
- [x] ทดสอบด้วย pytest (`backend/tests/test_pos.py`): checkout ตัดสต๊อก, ขายเกินสต๊อกถูกบล็อก, void คืนสต๊อก, หลายบิลพร้อมกัน, ส่วนลด, ยืนยัน draft order ตัดสต๊อกพูลเดียวกัน

### Frontend (Next.js)
- [x] หน้า `/products` — จัดการสินค้า (เพิ่ม/แก้ไข, ค้นหา, ปรับสต๊อกพร้อมหมายเหตุ, ไฮไลต์สต๊อกใกล้หมด)
- [x] หน้า `/pos` — ค้นหา/สแกนสินค้าด้วย SKU, ตะกร้าหลายบิล (tab พักบิล), ส่วนลดต่อรายการ/ต่อบิล, เลือกวิธีชำระ+คำนวณเงินทอน, พิมพ์ใบเสร็จ
- [x] `npm run build` ผ่าน ไม่มี TypeScript error

### โปรโมชั่น + UI revamp
- [x] โมเดล `Promotion`/`PromotionItem` (ลดราคาชั่วคราวตามช่วงเวลา + ซื้อคู่กันเป็นเซ็ต) — [backend/app/models.py](backend/app/models.py)
- [x] `app/services/promotions.py` — เช็คโปรที่ active, คำนวณราคาลด, คำนวณส่วนลด bundle ตามจำนวนเซ็ตที่ครบสูตรในบิล
- [x] เชื่อมเข้า POS: `add_item` snapshot ราคาลดอัตโนมัติ, `compute_totals` รวมส่วนลด bundle เป็น `promotion_discount`
- [x] REST API `/api/promotions` (list/create/update/toggle), `ProductOut`/`SaleOut` เพิ่ม `discounted_price`/`promotion_discount`
- [x] หน้า `/promotions` — สร้าง/ปิดเปิดโปรทั้ง 2 แบบ, แสดงสถานะ (ใช้งานอยู่/ยังไม่ถึง/หมดอายุ/ปิดใช้งาน)
- [x] โชว์ราคาโปรในหน้า `/pos` และ `/products`, โชว์ส่วนลด bundle ในสรุปยอด POS
- [x] ทดสอบด้วย pytest (`backend/tests/test_promotions.py`): ลดราคาในช่วงเวลา/นอกช่วงเวลา/ปิดใช้งาน, ส่วนลด bundle ตามจำนวนเซ็ต, toggle
- [x] ปรับ UI ทั้งระบบ: เพิ่ม sidebar เมนูถาวร (`frontend/app/components/Sidebar.tsx`), ใส่สีแบรนด์ (ส้ม/อำพัน) แทนปุ่มดำ-ขาวเดิม, ไอคอนจาก `lucide-react`, transition/hover ให้ดูมีชีวิตขึ้น

### หมายเหตุ
- Schema เปลี่ยน (ตารางใหม่ + คอลัมน์ใหม่ใน `products`) — ต้องลบ `dev.db`/ตาราง postgres เดิมแล้วให้ `create_all` สร้างใหม่ตอน restart backend เหมือน Phase 2/3
- ลองเชื่อม MinIO (`myserver:9000`) สำหรับเก็บรูปสินค้าแล้วแต่ต่อไม่ติด (timeout เหมือนกับ Postgres ตอนนั้น) — ยังไม่ได้ทำฟีเจอร์อัปโหลดรูปสินค้า รอ server กลับมาก่อน
- ยังไม่ทำ: รายงานเชิงลึกแยกราย SKU/แนวโน้มการขาย, รูปสินค้า
- ใบเสร็จผ่านเครื่องพิมพ์ thermal โดยตรง — ทำแล้ว ดูรายละเอียดในหัวข้อ 5.7 ด้านล่าง

## Phase 5: ระบบครบเครื่องสำหรับใช้งานจริง (gap analysis จากมุมแคชเชียร์ 10 ปี + ผู้ประกอบการรายย่อย)

### 5.1 ระบบผู้ใช้/สิทธิ์ (พื้นฐานของทุกอย่างข้างล่าง — ต้องทำก่อน)
- [x] โมเดล `User`/`Session` (username, password hash via bcrypt, role: owner/manager/cashier), session-cookie auth — [backend/app/models.py](backend/app/models.py), [backend/app/services/auth.py](backend/app/services/auth.py)
- [x] หน้า login (`/login`), `AuthGate` ป้องกันหน้า backoffice ทั้งหมด, ทุก router หลังบ้านต้องผ่าน `get_current_user`/`require_role` — [backend/app/deps.py](backend/app/deps.py), [frontend/app/components/AuthGate.tsx](frontend/app/components/AuthGate.tsx)
- [x] บันทึกว่าใครเป็นคนขาย/แก้ไข/ลบ ใน `Sale`, `StockMovement`, `Promotion` (`created_by_user_id`)
- [x] หน้าจัดการผู้ใช้ `/users` (owner เพิ่ม/ลบพนักงาน, กำหนด role) — [frontend/app/users/page.tsx](frontend/app/users/page.tsx)
- [x] สร้าง owner เริ่มต้น `admin`/`admin123` อัตโนมัติตอน startup ถ้ายังไม่มี user ในระบบ
- [x] ทดสอบด้วย pytest (`backend/tests/test_auth.py`): login/logout/me, 401 เมื่อไม่ login, 403 ตาม role, owner-only user management

### 5.2 ฟีเจอร์แคชเชียร์ประจำวัน
- [x] หน้า `/sales/history` — ดูบิลเก่า กรองตามวันที่/สถานะ — [frontend/app/sales/history/page.tsx](frontend/app/sales/history/page.tsx)
- [x] ปริ้นใบเสร็จซ้ำจากบิลเก่า (component ร่วม `Receipt.tsx` ใช้ทั้ง `/pos` และ `/sales/history`)
- [x] คืนสินค้า/คืนเงินบางรายการ (partial refund) — `refund_items()` คืนสต๊อกจริง, คืนครบทุกรายการ→status เปลี่ยนเป็น voided — [backend/app/services/pos.py](backend/app/services/pos.py)
- [x] แบ่งจ่ายหลายวิธีในบิลเดียว (เงินสด+โอน) ผ่าน `SalePayment`, คำนวณเงินทอนจากเงินสดส่วนเกินเท่านั้น
- [x] เปิดกะ/ปิดกะ (ใส่เงินทอนตั้งต้น, นับเงินปิดกะเทียบยอดที่ระบบคาดไว้) — [backend/app/services/shifts.py](backend/app/services/shifts.py), checkout ถูก block ถ้ายังไม่เปิดกะ
- [x] สรุปยอดท้ายกะ แยกเงินสด/โอน + ผลต่างเงินสดที่นับได้จริง
- [x] เลขใบเสร็จรันต่อเนื่องไม่ซ้ำ (`ReceiptCounter`, `with_for_update`)
- [x] ทดสอบด้วย pytest (`backend/tests/test_shifts_payments_refunds.py`): block checkout ไม่มีกะ, receipt_no รันต่อเนื่อง, เปิดกะซ้ำไม่ได้, split payment + สรุปยอดกะ, เงินทอนจากเงินสด, partial refund คืนสต๊อก/หักยอด, คืนครบ=voided, คืนเกินจำนวน=error, filter ประวัติบิลตามวันที่
- [x] คีย์ลัดคีย์บอร์ดในหน้า POS — `F2` โฟกัสช่องสแกน, `Ctrl+Z` ยกเลิกรายการล่าสุด, `F8` พักบิล, `F9` ชำระเงิน (เมื่อกดได้), `Esc` ปิดหน้าต่าง modal ที่เปิดอยู่ (เลือกตัวเลือกเสริม/QR/ปิดกะ) — ปิดใช้งานคีย์ลัดที่ชนกับการพิมพ์ในกล่องข้อความ (ยกเว้น F-key/Esc) — [frontend/app/pos/page.tsx](frontend/app/pos/page.tsx)
- [x] ปุ่ม Undo รายการล่าสุดในตะกร้า — จำสถานะก่อนเพิ่มสินค้าล่าสุด (ทั้งที่เพิ่มผ่านคลิก/สแกน/เลือกตัวเลือกเสริม และที่คิวไว้ระหว่างออฟไลน์) แล้วย้อนกลับเป็นจำนวนเดิมหรือลบรายการถ้าเป็นรายการใหม่ — สถานะ undo จะถูกล้างเมื่อสลับบิล/เปิดบิลใหม่/ชำระเงิน/แก้จำนวนรายการนั้นเอง เพื่อไม่ให้ undo ผิดรายการ — [frontend/app/pos/page.tsx](frontend/app/pos/page.tsx)

### 5.3 ฟีเจอร์ผู้ประกอบการ/บริหารร้าน
- [x] เพิ่มต้นทุนสินค้า (cost price) ต่อหน่วยใน `Product`, รายงานกำไรขั้นต้นจริง (ไม่ใช่แค่รายรับ-รายจ่ายรวม) — ทำใน 5.5 แล้ว ดูรายละเอียดด้านบน
- [x] ระบบ supplier + ใบสั่งซื้อ (purchase order) เชื่อมกับการเติมสต๊อก — โมเดล `Supplier`/`PurchaseOrder`/`PurchaseOrderItem` ([backend/app/models.py](backend/app/models.py)), รับสินค้าตาม PO จะเพิ่มสต๊อกจริงผ่าน `adjust_stock` และอัปเดต `cost_price` ของสินค้าให้ตรงต้นทุนล่าสุด ([backend/app/services/purchasing.py](backend/app/services/purchasing.py)), หน้า `/suppliers` จัดการซัพพลายเออร์+สร้าง/รับ/ยกเลิก PO (owner/manager เท่านั้น) — เทสต์ใน `backend/tests/test_suppliers_po.py`
- [x] สร้าง QR พร้อมเพย์จริงตอนเลือกชำระแบบโอน — เข้ารหัส payload ตามมาตรฐาน Thai EMV QR Code (TLV + CRC-16/CCITT) ไม่ต้องเรียก API ภายนอก ([backend/app/services/promptpay.py](backend/app/services/promptpay.py)), ตั้งเลขพร้อมเพย์ที่หน้า `/settings`, กดปุ่ม QR ข้างแถวชำระเงินแบบโอนในหน้า `/pos` เพื่อแสดง QR ให้ลูกค้าสแกน (ใช้ `qrcode.react` เรนเดอร์ฝั่งหน้าเว็บ) — เทสต์ใน `backend/tests/test_promptpay.py`
- [x] แจ้งเตือนสต๊อกใกล้หมดผ่าน LINE — ทำเป็น **plumbing ที่ตั้งค่าได้ ยังไม่ใช่การเชื่อมต่อจริง** เพราะร้านยังไม่มี LINE Official Account/Messaging API channel (ผู้ใช้ยืนยันแล้ว) — เพิ่มช่อง Channel Access Token + Target User/Group ID ในหน้า `/settings` พร้อมปุ่ม "ทดสอบส่งแจ้งเตือน" ที่เรียก LINE Messaging API push message จริงเมื่อตั้งค่าครบ ([backend/app/services/line_notify.py](backend/app/services/line_notify.py), `POST /api/settings/test-line-notify`) — **ยังไม่มีการส่งอัตโนมัติเมื่อสต๊อกใกล้หมด** ต้องกดทดสอบเอง/ต่อ cron ภายนอกเรียก endpoint นี้เพิ่ม — เทสต์ใน `backend/tests/test_line_notify.py` (mock การเรียก LINE API)
- [x] รายงานสินค้าขายดี/ขายไม่ดี (best seller / slow-moving) — `get_product_performance()` ([backend/app/services/accounting.py](backend/app/services/accounting.py)), `GET /api/reports/products` (owner/manager เท่านั้น), แสดงในหน้า `/reports` พร้อมสลับดูขายดี/ขายไม่ดี — เทสต์ใน `backend/tests/test_product_performance_report.py`
- [x] ข้อมูลลูกค้า/CRM พื้นฐาน + แต้มสะสม — โมเดล `LoyaltyCustomer`, ผูกกับ `Sale.customer_id` ตอน checkout ด้วยเบอร์โทร (สร้างลูกค้าใหม่อัตโนมัติถ้ายังไม่มี), สะสมแต้มตามอัตรา "กี่บาทต่อแต้ม" ที่ตั้งได้ในหน้า `/settings`, ใช้แต้มแลกส่วนลด 1 แต้ม = 1 บาทตอนชำระเงิน, หน้า `/customers` ดู/แก้ไขสมาชิก — เทสต์ใน `backend/tests/test_loyalty.py`
- [x] Export ข้อมูล (สินค้า/ยอดขาย/รายจ่าย) เป็น Excel/CSV — `GET /api/export/{products,sales,expenses}` คืนไฟล์ CSV (UTF-8 BOM เปิดใน Excel ได้ภาษาไทยไม่เพี้ยน), owner/manager เท่านั้น, ปุ่มดาวน์โหลดอยู่ในหน้า `/reports` ([backend/app/api/export.py](backend/app/api/export.py)) — เทสต์ใน `backend/tests/test_export.py`

### 5.4 โครงสร้าง/UX
- [x] ปรับ `/pos` ให้ใช้งานบนแท็บเล็ต/มือถือได้ (responsive) — Sidebar เปลี่ยนเป็น drawer เลื่อนเข้า/ออกพร้อมปุ่มแฮมเบอร์เกอร์บนมือถือ ([frontend/app/components/Sidebar.tsx](frontend/app/components/Sidebar.tsx)), หน้า POS ปรับ grid จาก 3 คอลัมน์คงที่เป็น 1 คอลัมน์บนมือถือ/3 คอลัมน์บนแท็บเล็ต-เดสก์ท็อป และตารางสินค้าปรับจำนวนคอลัมน์ตามขนาดหน้าจอ ([frontend/app/pos/page.tsx](frontend/app/pos/page.tsx)) — ทดสอบด้วยการ build ผ่าน ยังไม่ได้ทดสอบบนอุปกรณ์จริง
- [x] โหมดออฟไลน์ขายต่อได้เมื่อเน็ต/backend หลุด แล้ว sync ทีหลัง — **สโคปจำกัดเฉพาะ "เพิ่มสินค้าลงบิล" ระหว่างออฟไลน์**: ตรวจจับการหลุดเน็ตด้วย `navigator.onLine` + ping `/health` ทุก 10 วินาที, ถ้าเพิ่มสินค้าไม่สำเร็จเพราะเน็ตหลุด (ไม่ใช่ error จาก server) จะคิวคำสั่งไว้ใน localStorage และโชว์รายการ "ออฟไลน์ - รอซิงค์" ในตะกร้าทันที ใช้ราคาสินค้าที่แคชไว้ล่าสุด ([frontend/lib/offlineQueue.ts](frontend/lib/offlineQueue.ts), [frontend/app/pos/page.tsx](frontend/app/pos/page.tsx)), เมื่อเชื่อมต่อกลับมาจะยิงคำสั่งที่คิวไว้ตามลำดับแล้วรีเฟรชบิลจริงจากเซิร์ฟเวอร์อัตโนมัติ — **ข้อจำกัดที่ตั้งใจไว้**: ปุ่มชำระเงินจะถูกปิดไว้ตลอดเวลาที่ออฟไลน์หรือมีรายการค้างซิงค์ (เพราะการตัดสต๊อก/finalize ยอดต้องอาศัย backend จริงเพื่อความถูกต้อง), เปิดกะ/สร้างบิลใหม่/คืนเงิน/ยกเลิกบิลยังต้องมีการเชื่อมต่อเสมอ — ยังไม่มีเทสต์อัตโนมัติ (ต้องจำลองการตัดเน็ตซึ่งทำได้ยากใน pytest/headless build) ทดสอบด้วยมือโดยปิด backend แล้วลองสแกน/เพิ่มสินค้า

### 5.6 ข้อมูลสำหรับฝ่ายการตลาด (รีวิวมุมนักการตลาด — เพิ่มเข้า checklist แล้ว รอคำสั่ง implement)
- [ ] **priority สูงสุด** รายงานผลโปรโมชั่น — แต่ละโปรฯ ถูกใช้กี่ครั้ง ดันยอดขายเท่าไหร่ เสียส่วนลดไปเท่าไหร่ (วัด ROI ของแคมเปญ) — ปัจจุบันระบบลดราคาได้จริงแต่ไม่มีที่สรุปผลย้อนหลัง
- [ ] **priority สูง** รายงานลูกค้าใหม่ vs ลูกค้าซื้อซ้ำ (new vs returning) + รายชื่อลูกค้าที่เงียบไปนาน (win-back list) — ข้อมูล `Sale.customer_id`/`completed_at` มีอยู่แล้ว ขาดแค่ query สรุป (ไม่ต้องเพิ่มฟิลด์ใหม่)
- [ ] **priority ปานกลาง** ยอดขายเฉลี่ยต่อบิล (AOV) + จำนวนรายการเฉลี่ยต่อบิล ในหน้า `/reports`
- [ ] **priority ปานกลาง** กราฟยอดขายตามช่วงเวลา (ตามชั่วโมง/วันในสัปดาห์) — ใช้วางแผนโปรโมชั่นช่วงเวลา/จัดกำลังคน
- [ ] **priority ต่ำ** รายงานสินค้าที่ขายคู่กันบ่อย (basket affinity) — ใช้ออกแบบโปรโมชั่นมัดรวมใหม่ๆ จากข้อมูลจริงแทนการเดา
- [ ] **priority ต่ำ** Export "รายชื่อลูกค้า + ยอดซื้อสะสม + วันซื้อล่าสุด" สำหรับเอาไปยิงแคมเปญ/อัปขึ้นเครื่องมืออีเมล (ต่อจาก export CSV ที่มีอยู่)

### 5.7 ใบเสร็จ: PDF + พิมพ์ผ่านเครื่อง thermal (รีวิวมุมผู้เชี่ยวชาญ POS)
- [x] ปุ่ม "PDF" — แปลงใบเสร็จที่แสดงผลจริง (DOM) เป็นรูปภาพด้วย `html2canvas` แล้ววางใน PDF ด้วย `jspdf` ดาวน์โหลดเป็นไฟล์ทันที — เลี่ยงปัญหาฟอนต์ไทยของ `jspdf` ที่ไม่รองรับ Unicode ในฟอนต์เริ่มต้น เพราะใช้ฟอนต์ที่เบราว์เซอร์เรนเดอร์ไว้แล้วแทน — [frontend/lib/receiptPdf.ts](frontend/lib/receiptPdf.ts) ใช้ทั้งในหน้า `/pos` และ `/sales/history`
- [x] ปุ่ม "พิมพ์ผ่านเครื่อง" — เตรียม plumbing ไว้รอเชื่อมเครื่องพิมพ์ thermal/network จริง (เช่น Epson TM-T82, Star) **ยังไม่มีเครื่องจริงให้ทดสอบ**: ตั้งค่า IP + พอร์ต (ปกติ 9100) ที่หน้า `/settings`, backend สร้างคำสั่ง ESC/POS (encode ข้อความไทยด้วย `cp874`) แล้วส่งผ่าน raw TCP socket ตรงไปที่เครื่องพิมพ์ ([backend/app/services/thermal_printer.py](backend/app/services/thermal_printer.py), `POST /api/pos/sales/{id}/print-thermal`) — ถ้ายังไม่ตั้งค่า IP หรือเชื่อมต่อไม่ได้ จะแจ้ง error ที่หน้าเว็บและแนะนำให้ใช้ปุ่ม PDF แทน — เทสต์ใน `backend/tests/test_thermal_printer.py` (mock การส่ง socket เพราะไม่มีเครื่องจริง)
- [x] เอาปุ่ม "พิมพ์ใบเสร็จ" (window.print เดิม) ออก แทนด้วยสองปุ่มนี้ในทั้งหน้า `/pos` และ `/sales/history`

### 5.8 ตัดสต๊อก 2 แบบ (ขายปลีก/ร้านนั่งทาน) + ระบบนับสต๊อกจริง (stocktake)
- คุยกันก่อนทำ: ระบบ POS สำหรับร้านขายปลีกล้วนๆ กับร้านนั่งทาน/มีครัวต่างกันที่ "หน่วยของสต๊อก" — ขายปลีกขายเป็นหน่วยสำเร็จ (1 SKU = 1 ของที่นับได้) ตรงกับโมเดล `Product.stock_quantity` เดิมพอดี ส่วนร้านนั่งทานขายเมนูที่เป็นสูตร/วัตถุดิบหลายอย่าง สิ่งที่อยากนับจริงคือวัตถุดิบ ไม่ใช่จำนวนจานที่ขาย — จึงทำเป็น **ระบบตัดสต๊อก 2 แบบที่เลือกได้ในหน้า `/settings`** แทนการบังคับแบบเดียว
- [x] ตั้งค่า `inventory_mode` (`simple`/`recipe`) ในหน้า `/settings` — [backend/app/models.py](backend/app/models.py), [frontend/app/settings/page.tsx](frontend/app/settings/page.tsx)
- [x] โมเดล `Ingredient` (วัตถุดิบ: ชื่อ/หน่วย/สต๊อก/เตือนใกล้หมด), `RecipeItem` (สูตร: สินค้าใช้วัตถุดิบไหนกี่หน่วยต่อ 1 ชิ้นที่ขาย), `IngredientMovement` (ประวัติการเข้า-ออกวัตถุดิบ) — [backend/app/models.py](backend/app/models.py)
- [x] โหมด `simple` (ขายปลีก): ตัดสต๊อกสินค้าโดยตรงเหมือนเดิมทุกอย่าง ไม่กระทบของเก่า
- [x] โหมด `recipe` (ร้านนั่งทาน): ขายสินค้าที่ตั้งสูตรไว้ → ตัดสต๊อกวัตถุดิบตามสูตรอัตโนมัติ (ไม่แตะ `stock_quantity` ของสินค้านั้น) — **สินค้าที่ไม่ได้ตั้งสูตรจะ fallback ไปตัดสต๊อกของตัวเองตามปกติ** เพื่อให้ร้านนั่งทานที่มีของขายเป็นหน่วยสำเร็จด้วย (เช่น น้ำขวด) ใช้งานได้ในโหมดเดียวกัน — รวมศูนย์ตรรกะไว้ที่ `_apply_inventory_change()` ใช้ทั้ง checkout/void/refund ([backend/app/services/pos.py](backend/app/services/pos.py)) เพื่อให้คืนสต๊อกถูกต้องตามที่หักไปจริง
- [x] ตั้งสูตรสินค้าได้ที่หน้า `/products` (แก้ไขสินค้า → ส่วน "สูตร/วัตถุดิบ" ขึ้นเฉพาะตอนเปิดโหมด recipe), จัดการรายการวัตถุดิบ+ปรับสต๊อกที่หน้า `/ingredients` ใหม่ — `GET/PUT /api/products/{id}/recipe`, `/api/ingredients` (CRUD + stock-adjustment)
- [x] ระบบนับสต๊อกจริง (stocktake) — เปิดรอบนับ → ระบบ snapshot สต๊อกปัจจุบันเป็น "ค่าที่คาดไว้" ของทุกสินค้า (โหมด simple) หรือวัตถุดิบทุกตัว (โหมด recipe) ให้กรอกจำนวนที่นับได้จริงทีละรายการ → ปิดรอบจะปรับสต๊อกให้ตรงกับที่นับได้ (สร้าง stock movement reason `stocktake`), รายการที่ไม่ได้กรอกจะถูกข้ามไม่ปรับ — เปิด/ปิดรอบจำกัดแค่ owner/manager, กรอกจำนวนนับทำได้ทุก role (พนักงานช่วยนับได้) — หน้า `/stocktake` ใหม่, `POST/GET /api/stocktake/sessions`, `PUT .../lines/{id}`, `POST .../close`, เปิดพร้อมกัน 2 รอบไม่ได้
- [x] เทสต์ใน `backend/tests/test_inventory_recipe_stocktake.py`: โหมด simple ตัดสต๊อกสินค้าเหมือนเดิม (regression), โหมด recipe ตัดวัตถุดิบตามสูตรไม่แตะสต๊อกสินค้า, สินค้าไม่มีสูตร fallback ตัดสต๊อกตัวเอง, void/refund คืนวัตถุดิบถูกต้อง (เต็ม/บางส่วน), เปิดรอบนับสต๊อกสร้าง snapshot ถูก entity ตามโหมด, ปิดรอบปรับสต๊อกถูกต้อง+ข้ามรายการที่ไม่ได้นับ, เปิดรอบซ้ำขณะมีรอบเปิดอยู่ถูกบล็อก, ลบวัตถุดิบที่ถูกใช้ในสูตรอยู่ถูกบล็อก
- [x] `npm run build` ผ่าน, รัน pytest ทั้งชุดผ่านหมด (ไม่มี regression จากการแก้ checkout/void/refund เดิม)

### 5.9 ตั้งค่าเลือกฐานข้อมูล (สลับ SQLite ↔ PostgreSQL จากหน้าตั้งค่า)
- บริบท: เดิมเลือก DB ได้แค่ผ่านการแก้ไฟล์ `.env` ด้วยมือ (เคยสลับจาก Postgres `myserver` มาเป็น sqlite local ชั่วคราวตอน server ต่อไม่ติด) — ตอนนี้ทำเป็นหน้าตั้งค่าให้สลับได้โดยไม่ต้องแก้ไฟล์เอง
- [x] เก็บค่าที่เลือกไว้ใน `backend/db_config.json` (อยู่นอกฐานข้อมูลเอง เพราะต้องอ่านได้ก่อนเชื่อมต่อ DB) — gitignore ไว้แล้วเพราะอาจมี connection string/รหัสผ่าน Postgres — [backend/app/db_config.py](backend/app/db_config.py)
- [x] ลำดับความสำคัญตอน resolve URL จริง: env var `DATABASE_URL` (ใช้โดย pytest/deploy override) > `db_config.json` (ตั้งจากหน้าเว็บ) > ค่า default จาก `.env`/`config.py` เดิม — ทำให้ฟีเจอร์นี้ไม่กระทบเทสต์เดิมเลยเพราะทุกไฟล์เทสต์ set `DATABASE_URL` ก่อน import เสมอ
- [x] **ต้อง restart backend หลังเปลี่ยนค่าถึงจะมีผลจริง** (ตั้งใจไม่ทำ hot-swap engine ขณะรันอยู่ เพราะเสี่ยง connection ค้าง/schema ไม่ตรงระหว่างสลับ — ตรงกับแนวทางเดิมของระบบที่ไม่มี migration tool ต้อง restart เมื่อ schema เปลี่ยนอยู่แล้ว)
- [x] `GET/PUT /api/system/db-config` (owner เท่านั้น เพราะอาจมีรหัสผ่าน DB), `POST /api/system/db-config/test` ทดสอบเชื่อมต่อจริงก่อนบันทึก (กัน role อื่นเห็น/แก้ connection string) — [backend/app/api/system.py](backend/app/api/system.py)
- [x] หน้า `/settings` ส่วนใหม่ (โชว์เฉพาะ owner): เลือก SQLite (ระบุ path ไฟล์) หรือ PostgreSQL (กรอก connection string ในช่อง password-type), ปุ่ม "ทดสอบการเชื่อมต่อ" + "บันทึก" พร้อมข้อความเตือนต้อง restart, แจ้งเตือนถ้ามี `DATABASE_URL` จาก env var ทับอยู่ (ตั้งในหน้านี้จะไม่มีผลจนกว่าจะเอา env var ออก)
- [x] เทสต์ใน `backend/tests/test_db_config.py`: ต้องเป็น owner เท่านั้นถึงเข้าได้ (manager โดน 403), ค่า default ตอนยังไม่มีไฟล์, validation (engine ไม่รู้จัก/postgres ไม่กรอก connection string), บันทึกแล้วอ่านกลับมาตรง, ทดสอบเชื่อมต่อ sqlite สำเร็จ/postgres ปลอมไม่สำเร็จ

### 5.5 รีวิวรอบ 2 (มุมแคชเชียร์ใช้มาหลายระบบ + ผู้ประกอบการ)
- [x] แก้บั๊ก: คืนเงินบางรายการแล้วรายงานรายรับยังไม่หักยอดที่คืน (`accounting.py` นับยอดเกินจริง)
- [x] ใบเสร็จแสดงชื่อร้าน/ที่อยู่/เลขผู้เสียภาษี (เพิ่ม field ใน `ShopSettings` + แก้ไขที่หน้า `/settings` + แสดงใน `Receipt.tsx`)
- [x] ปุ่มลัดจำนวนเงินสดในหน้า POS (พอดี/+20/+50/+100) — [frontend/app/pos/page.tsx](frontend/app/pos/page.tsx)
- [x] ตั้งชื่อ/หมายเหตุบิลที่พักไว้ให้เห็นในแท็บ (เช่น ชื่อลูกค้า/โต๊ะ) — [frontend/app/pos/page.tsx](frontend/app/pos/page.tsx)
- [x] Quick-lock หน้าจอ + PIN สั้นสลับผู้ใช้โดยไม่ต้อง login เต็มรูปแบบ — `pin_hash`/`/api/auth/unlock`/`/api/auth/set-pin` ([backend/app/api/auth.py](backend/app/api/auth.py)), `LockScreen.tsx` + ปุ่มล็อก/ตั้ง PIN ใน `Sidebar.tsx` — เทสต์ใน `backend/tests/test_auth.py`
- [x] หมวดหมู่สินค้า (category) ใน `Product` + filter/แท็บหมวดในหน้า POS และ `/products` — เทสต์ใน `backend/tests/test_product_categories.py`
- [x] ระบบตัวเลือกเสริมสินค้า (modifier/add-on เช่น ท็อปปิ้ง/ซอส) พร้อมราคาเสริม เลือกตอนเพิ่มลงตะกร้า — โมเดล `ProductModifier`/`SaleItemModifier`, จัดการที่หน้า `/products` (แก้ไขสินค้า), เลือกตอนกดสินค้าในหน้า `/pos` ถ้ามีตัวเลือก — เทสต์ใน `backend/tests/test_product_modifiers.py`
- [x] ต้นทุนสินค้า (cost price) ต่อหน่วยใน `Product` + กำไรขั้นต้นจริงในหน้า `/reports` — เห็นต้นทุนได้เฉพาะ owner/manager (`cost_price` ถูกซ่อนเป็น 0 สำหรับ cashier ทั้ง backend และ frontend) — เทสต์ใน `backend/tests/test_cost_price_gross_margin.py`
- [x] หน้า dashboard สรุปวันนี้ (ยอดขายวันนี้, จำนวนบิล, สต๊อกใกล้หมด, กะที่เปิดอยู่) — [frontend/app/page.tsx](frontend/app/page.tsx), `/api/reports/today` (owner/manager เห็นยอดขาย, cashier เห็นแค่สถานะกะตัวเอง)
- [x] หน้า audit log ดูการคืนเงิน/ยกเลิกบิลทั้งหมด (ใครทำ เมื่อไหร่ เหตุผล) สำหรับ owner/manager — โมเดล `SaleAuditLog` บันทึกตอน void บิลที่ชำระแล้ว/refund (ไม่บันทึกตอนยกเลิกบิลที่ยังพักอยู่เพราะไม่ใช่ของจริง), หน้า `/audit` — เทสต์ใน `backend/tests/test_audit_log.py`
- [x] รีวิวรอบ 3 (หลังทำครบ 5.5): เรียกมุมแคชเชียร์ + ผู้ประกอบการมาตรวจซ้ำ — แคชเชียร์เจอบั๊กจริง: สแกนบาร์โค้ดสินค้าที่มี modifier จะข้าม picker แล้วเพิ่มเข้าตะกร้าแบบไม่มี topping ทันที (ต่างจากตอนคลิกเมาส์ที่เปิด picker) — แก้แล้วโดยให้ `handleScanSubmit` เรียก `api.lookupProduct` เช็ค modifiers ก่อนเสมอ ([frontend/app/pos/page.tsx](frontend/app/pos/page.tsx)); ผู้ประกอบการยืนยันว่าตอนนี้ตอบคำถาม "กำไรขั้นต้นจริง/ใครคืนเงินบ่อย/สต๊อกใกล้หมดวันนี้" ได้แล้ว แต่ยังตอบ "สินค้าขายดี/ขายไม่ดี" และ "แจ้งเตือนสต๊อกอัตโนมัติ" ไม่ได้ (อยู่ใน 5.3 ที่ยังไม่ทำ) — ดูรายละเอียดเต็มในบทสรุปท้ายเซสชัน

### หมายเหตุ
- สโคปใหญ่มาก แบ่งทำเป็นรอบ — เริ่มจาก 5.1 (auth) ก่อนเพราะทุกฟีเจอร์ที่เหลือต้องรู้ว่า "ใคร" ทำรายการ
- ทำทีละ sub-phase แล้ว build+test ให้ผ่านก่อนค่อยไปต่อ ไม่ทำทุกอย่างพร้อมกันในคอมมิตเดียว
- 5.1 และ 5.2 เสร็จและผ่านการทดสอบแล้ว (pytest 31 ข้อผ่านหมด, `npm run build` ผ่าน, ทดสอบจริงผ่าน curl: login → เปิดกะ → ขายแบบแบ่งจ่าย → คืนเงินบางรายการ → ปิดกะ → ดูประวัติบิล)
- **สำคัญ:** ระบบสร้าง user เริ่มต้น `admin`/`admin123` (role owner) อัตโนมัติถ้ายังไม่มี user ในระบบ — ต้องรีบเปลี่ยนรหัสผ่านหลังติดตั้งจริง (เปลี่ยนได้ที่หน้า `/users`)
- รอบทบทวนสิทธิ์ (audit) เพิ่มเติม: cashier ยกเลิก/คืนเงินบิลที่ชำระแล้วไม่ได้ (ต้องผู้จัดการ/เจ้าของร้าน), cashier ปิดกะ/ดูสรุปยอดกะของคนอื่นไม่ได้ (เฉพาะกะตัวเอง หรือผู้จัดการ/เจ้าของร้านดูได้ทุกกะ) — เทสต์ใน `backend/tests/test_role_permission_gaps.py`
- 5.3 และ 5.4 ทำครบทุกข้อแล้ว (pytest รวม 85 ข้อผ่านหมด, `npm run build` ผ่าน) — ดูรายละเอียดและข้อจำกัดของแต่ละฟีเจอร์ในหัวข้อด้านบน โดยเฉพาะ LINE notify (ยังไม่มี LINE OA จริงให้เชื่อม) และโหมดออฟไลน์ (จำกัดเฉพาะการเพิ่มสินค้า ไม่รวมการชำระเงิน/เปิดกะ)
- คีย์ลัดคีย์บอร์ดในหน้า POS และปุ่ม Undo รายการล่าสุด (ค้างจาก 5.2) ทำเสร็จแล้ว ดูรายละเอียดในหัวข้อ 5.2 ด้านบน
- ยังไม่ได้ทำ: ทดสอบโหมดออฟไลน์/responsive บนอุปกรณ์จริง (ทำแค่ build ผ่าน), ส่งแจ้งเตือน LINE สต๊อกใกล้หมดแบบอัตโนมัติ (ตอนนี้ต้องกดทดสอบเอง/ต่อ cron ภายนอกเรียก endpoint)
- รีวิวมุมนักการตลาด (2026-06-27): เพิ่ม backlog 5.6 (รายงานผลโปรโมชั่น, ลูกค้าใหม่/ซื้อซ้ำ, AOV, ยอดขายตามช่วงเวลา, basket affinity, export รายชื่อลูกค้า) — รอคำสั่ง implement
- รีวิวมุมผู้เชี่ยวชาญ POS รอบเดียวกัน: เสนอเพิ่มวันเกิด/flag ยินยอมรับข่าวสาร/วันซื้อล่าสุด/tag-segment ใน `LoyaltyCustomer` — **เจ้าของร้านพิจารณาแล้วว่ายังไม่จำเป็นตอนนี้ ไม่เพิ่มเข้า backlog** (นอกเหนือจากนี้ฝั่งปฏิบัติการ POS ถือว่าครบตามที่รีวิวไปแล้วในรอบก่อนๆ)
