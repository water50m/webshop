export const legal = {
  businessName: process.env.NEXT_PUBLIC_LEGAL_BUSINESS_NAME || "SStore",
  contactEmail: process.env.NEXT_PUBLIC_LEGAL_CONTACT_EMAIL || "",
  effectiveDate: process.env.NEXT_PUBLIC_LEGAL_EFFECTIVE_DATE || "[กรอกวันที่มีผลบังคับใช้ก่อนเปิดใช้งานจริง]",
};

export function contactText() {
  return legal.contactEmail || "[กรอกอีเมลติดต่อก่อนเปิดใช้งานจริง]";
}
