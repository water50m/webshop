import Link from "next/link";
import { contactText, legal } from "../legal";

export default function TermsPage() {
  return <main className="mx-auto max-w-3xl p-6 text-sm leading-7 text-slate-700">
    <h1 className="text-2xl font-bold text-slate-900">ข้อกำหนดการใช้บริการ</h1>
    <p className="mt-2">มีผลบังคับใช้: {legal.effectiveDate}</p>
    <p className="mt-5">SStore เป็นระบบหลังบ้านที่ {legal.businessName} จัดให้เพื่อช่วยร้านจัดการข้อความและออเดอร์จาก Facebook Page ที่เจ้าของเพจเลือกเชื่อมต่อ การใช้บริการถือว่าคุณยอมรับข้อกำหนดนี้</p>
    <h2 className="mt-7 text-lg font-semibold text-slate-900">1. บัญชีและสิทธิ์</h2>
    <p>ผู้ใช้ต้องใช้บัญชี SStore ของตนเองและรักษาความลับของรหัสผ่าน เจ้าของร้านเป็นผู้รับผิดชอบการเพิ่ม ลบ และกำหนดสิทธิ์ของทีมร้าน ผู้ใช้เห็นและดำเนินการกับ Inbox ได้เฉพาะเพจที่ได้รับสิทธิ์ใน SStore</p>
    <h2 className="mt-7 text-lg font-semibold text-slate-900">2. การเชื่อมต่อ Facebook Page</h2>
    <p>เฉพาะผู้ที่มีสิทธิ์จัดการ Facebook Page และมีสิทธิ์เจ้าของเพจใน SStore เท่านั้นที่เชื่อมต่อหรือยกเลิกการเชื่อมต่อได้ การเชื่อมต่อใช้ Facebook Login เพื่อขอสิทธิ์ที่จำเป็นต่อการรับและส่ง Messenger หลังเชื่อมแล้ว พนักงานร้านใช้บัญชี SStore ของตนเอง ไม่จำเป็นต้องใช้บัญชี Facebook ของกันและกัน</p>
    <h2 className="mt-7 text-lg font-semibold text-slate-900">3. การใช้งานที่รับผิดชอบ</h2>
    <p>ผู้ใช้ต้องตรวจสอบข้อความ ราคา สต็อก และออเดอร์ก่อนตอบหรือยืนยัน และต้องไม่ใช้บริการเพื่อส่งสแปม หลอกลวง ละเมิดสิทธิ์ผู้อื่น หรือฝ่าฝืนข้อกำหนดของ Meta และกฎหมายที่เกี่ยวข้อง เจ้าของร้านรับผิดชอบต่อการสื่อสารและการปฏิบัติตามคำสั่งซื้อของร้านตน</p>
    <h2 className="mt-7 text-lg font-semibold text-slate-900">4. การระงับหรือเปลี่ยนแปลงบริการ</h2>
    <p>เราอาจปรับปรุง ระงับ หรือจำกัดบริการเมื่อจำเป็นต่อความมั่นคง ความปลอดภัย การบำรุงรักษา หรือการปฏิบัติตามข้อกำหนดของ Meta เราไม่รับประกันว่าบริการของ Meta หรือการส่งข้อความจะพร้อมใช้งานโดยไม่มีการขัดข้องตลอดเวลา</p>
    <h2 className="mt-7 text-lg font-semibold text-slate-900">5. การยกเลิกและลบข้อมูล</h2>
    <p>การยกเลิกการเชื่อมต่อจะหยุดการใช้ Page Access Token ของเพจนั้น แต่ไม่ใช่การลบประวัติข้อมูลโดยอัตโนมัติ เจ้าของเพจสามารถสั่งลบข้อมูลรายเพจอย่างถาวรได้จากระบบ หรือใช้ <Link className="text-blue-700 underline" href="/data-deletion">หน้าคำแนะนำการขอลบข้อมูล</Link></p>
    <h2 className="mt-7 text-lg font-semibold text-slate-900">6. ติดต่อ</h2>
    <p>ติดต่อ {contactText()} หากมีคำถามเกี่ยวกับบริการหรือข้อกำหนดนี้</p>
  </main>;
}
