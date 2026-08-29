# SStore — Phase 1: รับ Order จาก Meta (Messenger + Instagram DM)

ระบบรับข้อความจาก Facebook Page Messenger และ Instagram DM เข้ามาเป็น "draft order"
ให้พนักงานตรวจสอบและกดยืนยันในหน้า back-office (Next.js) — ดูรายละเอียด design เต็มได้ที่
`C:\Users\pmach\.claude\plans\pos-cozy-giraffe.md`

## โครงสร้างโปรเจกต์
- `backend/` — FastAPI: รับ webhook จาก Meta, เก็บข้อความ, จับคู่สินค้า, สร้าง draft order, expose REST API
- `frontend/` — Next.js: หน้า inbox ดูข้อความ และหน้าตรวจ/ยืนยัน draft order

## การใช้งาน Back-office

- หน้าจอที่กว้างตั้งแต่ 640px ขึ้นไปจะแสดง sidebar แบบ desktop และสามารถยุบ/ขยายได้จากปุ่มในแถบเมนู
- บนมือถือ เมนูจะเปิดเป็น drawer จากปุ่มด้านบน และจะปิดเองเมื่อเลือกเมนูหรือแตะพื้นที่ด้านนอก
- หน้าเริ่มต้นอยู่ที่ `/` และปุ่ม **เริ่มขาย (POS)** จะพาไปที่ `/pos`

การพัฒนา frontend เปิดใช้งานได้ทั้งเครื่องเดียวกันและอุปกรณ์ใน private LAN โดย Next.js จะ bind ที่ `0.0.0.0:3000` อัตโนมัติ:

```bash
cd frontend
npm run dev
```

เปิดจากอุปกรณ์อื่นด้วย `http://<computer-ip>:3000` โดยไม่ต้องแก้ source code หรือกำหนด IP ตายตัว

## 1) ติดตั้งและรัน Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
copy .env.example .env           # แล้วแก้ค่าใน .env
```

ตั้งค่า `.env`:
- `DATABASE_URL` — connection string ของ PostgreSQL ที่ต้องสร้างไว้ล่วงหน้า (เช่น `createdb sstore`)
  - ทดสอบโดยไม่มี Postgres ได้ด้วย sqlite: `DATABASE_URL=sqlite:///./dev.db`
- `META_VERIFY_TOKEN` — ตั้งเป็น string สุ่มเอง (ใช้ตอน verify webhook กับ Meta)
- `META_APP_SECRET` — จาก Meta App settings (ใช้ตรวจ signature ของ webhook; ถ้าเว้นว่างจะข้ามการตรวจสอบ ใช้ได้เฉพาะตอน dev เท่านั้น)

รันเซิร์ฟเวอร์:
```bash
uvicorn app.main:app --reload --port 8000
```

ทดสอบว่าระบบทำงาน: เปิด http://localhost:8000/health ต้องได้ `{"status": "ok"}`

ตอนเริ่มต้นต้องเพิ่มสินค้าลง DB เองก่อน (ยังไม่มีหน้าจัดการสินค้าใน Phase 1) เช่นผ่าน Python shell:
```python
from app.db import SessionLocal
from app.models import Product
db = SessionLocal()
db.add(Product(sku="SKU1", name="เสื้อยืดสีขาว", price=199))
db.commit()
```

## 2) ติดตั้งและรัน Frontend

```bash
cd frontend
copy .env.local.example .env.local   # ตรวจว่า NEXT_PUBLIC_API_BASE_URL ชี้ไป backend ถูกต้อง
npm install
npm run dev
```

เปิด http://localhost:3000 — มีลิงก์ไปหน้า **Inbox** (ดูข้อความ) และ **Draft Orders** (ตรวจ/ยืนยันออเดอร์)

## 3) เปิด Tunnel ให้ Meta เรียก Webhook ได้ (local dev)

Meta ต้องเรียก webhook ผ่าน public HTTPS URL เลือกใช้ ngrok หรือ cloudflared อย่างใดอย่างหนึ่ง:

```bash
# ngrok
ngrok http 8000

# หรือ cloudflared
cloudflared tunnel --url http://localhost:8000
```

จะได้ URL แบบ `https://xxxx.ngrok-free.app` หรือ `https://xxxx.trycloudflare.com` — webhook endpoint ของเราอยู่ที่ `/webhooks/meta` ดังนั้น Callback URL ที่ใส่ใน Meta App คือ:
```
https://xxxx.ngrok-free.app/webhooks/meta
```

## 4) ตั้งค่า Meta App (ครั้งแรกต้องทำตามนี้)

1. ไปที่ https://developers.facebook.com/apps → สร้าง App ใหม่ ประเภท **Business**
2. ใน App เพิ่ม Product: **Messenger** และ **Instagram**
3. ในหน้า Messenger → Settings → ผูก Facebook Page ที่ต้องการ → กด Generate Token จะได้ Page Access Token (เก็บไว้ใส่ `.env` เป็น `META_PAGE_ACCESS_TOKEN` — Phase 1 ยังไม่ใช้ส่งข้อความออก แต่เตรียมไว้)
4. ในหน้า Instagram → ผูก IG Business account ที่ลิงก์กับ Page เดียวกัน → ขอ permission `instagram_basic`, `instagram_manage_messages`
5. ตั้งค่า Webhook:
   - Callback URL: ใส่ tunnel URL จากขั้นตอนที่ 3 (ลงท้ายด้วย `/webhooks/meta`)
   - Verify Token: ใส่ค่าเดียวกับ `META_VERIFY_TOKEN` ใน `.env`
   - กด Verify and Save (backend ต้องรันอยู่ก่อน ไม่งั้น verify ไม่ผ่าน)
   - Subscribe field: `messages` (สำหรับทั้ง Page และ Instagram)
6. ใน App settings → Basic → คัดลอก App Secret มาใส่ `META_APP_SECRET` ใน `.env` (จำเป็นสำหรับตรวจสอบว่า webhook มาจาก Meta จริง)
7. เพิ่มบัญชี Facebook ของคุณเป็น **Tester** ใน App Roles เพื่อทดสอบได้โดยไม่ต้องรอ App Review

## 4.1) ตั้งค่า LINE Official Account

1. ไปที่ https://developers.line.biz/console/ → สร้าง Provider → สร้าง Channel ประเภท **Messaging API**
2. ในแท็บ **Messaging API** ของ channel:
   - คัดลอก **Channel secret** มาใส่ `.env` เป็น `LINE_CHANNEL_SECRET` (ใช้ตรวจ header `X-Line-Signature` ว่า webhook มาจาก LINE จริง)
   - ตั้ง **Webhook URL** เป็น tunnel URL ลงท้ายด้วย `/webhooks/line` เช่น `https://xxxx.ngrok-free.app/webhooks/line`
   - เปิด **Use webhook**
   - ปิด **Auto-reply messages** และ **Greeting messages** (กันบอทเริ่มต้นของ LINE ไปตอบลูกค้าซ้อนกับระบบเรา)
3. กด **Verify** ในหน้า Webhook settings เพื่อทดสอบว่า backend ตอบ 200 (backend ต้องรันอยู่ก่อน)
4. เพิ่มเพื่อน LINE OA ของคุณเอง (สแกน QR ในหน้า Channel) แล้วลองทักแชทเข้ามาได้เลย — ไม่ต้องรอ approve เหมือน Meta

## 5) ทดสอบ end-to-end

1. รัน backend + tunnel + frontend ให้พร้อม และตั้ง webhook ผ่านแล้ว
2. ใช้บัญชี Facebook/Instagram ส่วนตัว (ที่เพิ่มเป็น tester) ส่งข้อความถึง Page/IG เช่น "สนใจเสื้อยืดสีขาว 1 ตัว"
3. เปิด http://localhost:3000/inbox ควรเห็นข้อความเข้ามา
4. เปิด http://localhost:3000/orders/draft ควรเห็น draft order ที่จับคู่สินค้าได้ (ชื่อสินค้าต้องตรงกับที่มีใน DB)
5. กด "ยืนยัน" — สถานะของ draft order ต้องเปลี่ยนเป็น confirmed

## การประมวลผลข้อความคำสั่งซื้อ (Meta + LINE)

ทุกข้อความที่เข้ามาจาก Facebook Messenger, Instagram DM และ LINE OA จะถูกประมวลผลด้วย
`backend/app/services/order_parser.py` ตามลำดับ (เฉพาะข้อความที่เพิ่งส่งเข้ามาเท่านั้น
ไม่ดึงประวัติแชทเก่ามาตีความซ้ำ):

1. จัดประเภทข้อความว่าเป็นทักทาย/คำถาม/ข้อความสั่งซื้อ — ถ้าเป็นทักทายหรือคำถามล้วนๆ จะไม่สร้าง draft order
2. ค้นหาคำในข้อความที่ตรงกับชื่อเมนู (Product), ท็อปปิ้ง (ProductModifier) หรือวัตถุดิบ (Ingredient) ในระบบ
3. เช็คคำนำหน้าคำที่ match แต่ละคำ (8 ตัวอักษรก่อนหน้า) ว่ามีคำปฏิเสธ เช่น "ไม่", "ไม่ใส่", "ไม่เอา", "งด" หรือไม่ — เมนูที่ถูกปฏิเสธจะไม่ถูกเพิ่มเข้า draft order, ท็อปปิ้ง/วัตถุดิบที่ถูกปฏิเสธจะถูกบันทึกเป็น special request (เช่น "ไม่ใส่ถั่ว") ติดกับรายการเมนูที่อยู่ก่อนหน้าในข้อความเดียวกัน

ดู `backend/tests/test_order_parser.py` สำหรับตัวอย่างเคสที่ครอบคลุม และดูหัวข้อ "ข้อจำกัดของการตีความคำสั่งซื้อ" ด้านล่างสำหรับสิ่งที่ยังตีความผิดได้

### เลือกได้ว่าจะใช้ Algorithm ดิบ หรือ AI

ในหน้า `/settings` มีตัวเลือก **"ระบบตีความข้อความสั่งซื้อ"**:
- **Algorithm ดิบ (ค่าเริ่มต้น)** — ใช้ `order_parser.py` ตามที่อธิบายข้างบน ไม่ต้องตั้งค่าเพิ่ม ไม่มีค่าใช้จ่าย
- **AI** — ต้องใส่ Anthropic API Key ในหน้าตั้งค่า ระบบจะส่งรายการเมนู/ท็อปปิ้ง/วัตถุดิบทั้งหมด
  พร้อมข้อความลูกค้าไปให้ Claude (`backend/app/services/ai_order_parser.py`) ตีความแทน — เข้าใจภาษาธรรมชาติได้กว้างกว่า
  แต่มีค่าใช้จ่ายต่อข้อความ และ AI ถูกบังคับให้ตอบชื่อที่ตรงกับ catalog เป๊ะๆเท่านั้น (ชื่อที่ไม่อยู่ในระบบจะถูกข้ามทิ้ง
  ไม่ใช้ชื่อที่ AI เดาขึ้นมาเอง)
- ถ้าเลือกโหมด AI แต่เรียก API ไม่สำเร็จ (ไม่มี key, เน็ตล่ม, API ตอบ error) ระบบจะ**ตกกลับไปใช้ algorithm ดิบให้อัตโนมัติ**
  สำหรับข้อความนั้น ไม่ทิ้งข้อความลูกค้าไปเฉยๆ

## ขอบเขตที่ยังไม่ทำใน Phase 1
- ยังไม่ตัดสต๊อกจริงตอนสร้าง draft order (ตัดตอนกด "ยืนยัน" เท่านั้น) ไม่มี POS ไม่มีคำนวณภาษี (เป็น phase ถัดไป)
- การจับคู่สินค้า/ท็อปปิ้ง/วัตถุดิบเป็น keyword matching ง่ายๆ (ชื่อต้องอยู่ในข้อความตรงตัว) ยังไม่ใช้ NLU จริง
- ยังไม่ตอบกลับลูกค้าอัตโนมัติบน LINE/Meta (ไม่มีการส่งข้อความออกเลย แค่รับเข้า)

### ข้อจำกัดของการตีความคำสั่งซื้อ (ตอบคำถาม "ครอบคลุมหรือยัง")
- **แยกทักทาย/คำถามด้วย keyword list ตายตัว** ไม่ใช่ NLU จริง ประโยคทักทาย/คำถามที่ไม่อยู่ในลิสต์ (เช่น สแลง, ภาษาพูดแปลกๆ, พิมพ์ผิด) จะถูกตีความเป็นออเดอร์ผิดพลาด และในทางกลับกัน ประโยคสั่งซื้อที่บังเอิญมีคำอย่าง "ไหม" อยู่ในชื่อสินค้า (เช่น สินค้าชื่อ "หมูไหม้") จะถูกเข้าใจผิดว่าเป็นคำถาม
- **ระยะเช็คคำปฏิเสธอยู่ที่ 8 ตัวอักษรก่อนหน้าคำที่ match เท่านั้น** ถ้าลูกค้าพิมพ์ "ไม่เอาถั่วนะคะ" (มีคำอื่นคั่นไกลเกิน 8 ตัวอักษร) ระบบอาจตรวจไม่เจอคำปฏิเสธ
- **ไม่รองรับจำนวน/หน่วยนับ** เช่น "ส้มตำ 2 จาน" ระบบจะเข้าใจว่าเป็น 1 รายการเสมอ (ลูกค้าต้องพิมพ์ชื่อเมนูซ้ำ 2 ครั้งถ้าต้องการให้ระบบนับเป็น 2)
- **ไม่เข้าใจคำพ้องความหมายหรือคำย่อ** ชื่อในข้อความต้องตรงกับชื่อในระบบแบบ substring เป๊ะๆ (ไม่สนตัวพิมพ์เล็ก/ใหญ่) — "ผัดไทย" จะไม่ match กับสินค้าชื่อ "ผัดไทยกุ้งสด" ถ้าคำว่า "ผัดไทยกุ้งสด" ไม่ปรากฏในข้อความ
- **ท็อปปิ้ง/วัตถุดิบที่ปฏิเสธแล้วไม่มีเมนูอยู่ก่อนหน้าในข้อความเดียวกัน** จะถูกแนบเป็น note ของ draft order ทั้งใบแทน (ไม่รู้ว่าลูกค้าหมายถึงเมนูไหน) และถ้ายังไม่มี draft order ที่เปิดอยู่เลย ข้อความนั้นจะถูกข้ามไปเฉยๆ (ไม่ถูกบันทึกเป็นคำสั่งอะไร)
- **ไม่มี context ข้ามข้อความ** ถ้าลูกค้าพิมพ์ "ขอผัดไทย" ข้อความหนึ่ง แล้วพิมพ์ "ไม่ใส่ถั่ว" อีกข้อความถัดมา ระบบจะแนบ "ไม่ใส่ถั่ว" เป็น note ของ draft order ทั้งใบ (ไม่ได้ผูกกับรายการผัดไทยโดยเฉพาะ เพราะกฎข้อ 4 กำหนดให้เช็คเฉพาะคำที่เพิ่งส่งมาในข้อความนั้นๆ)
- **พนักงานต้องตรวจทุกครั้งก่อนยืนยัน** — เพราะข้อจำกัดข้างต้น ระบบจึงออกแบบให้เป็น draft เสมอ ไม่ auto-confirm
- ยังไม่ส่งข้อความตอบกลับลูกค้าอัตโนมัติ (เช่น "ได้รับออเดอร์แล้ว")
- ยังไม่มีหน้าจัดการสินค้า (เพิ่ม/แก้ไขสินค้าต้องทำผ่าน DB ตรงๆ ก่อน)
