import httpx

from app.models import Product

LINE_PUSH_URL = "https://api.line.me/v2/bot/message/push"


def send_line_message(channel_access_token: str, target_id: str, text: str) -> None:
    if not channel_access_token or not target_id:
        raise ValueError("ยังไม่ได้ตั้งค่า LINE Channel Access Token หรือ Target ID ในหน้าตั้งค่า")
    response = httpx.post(
        LINE_PUSH_URL,
        headers={"Authorization": f"Bearer {channel_access_token}", "Content-Type": "application/json"},
        json={"to": target_id, "messages": [{"type": "text", "text": text}]},
        timeout=10,
    )
    if response.status_code >= 400:
        raise ValueError(f"LINE API ตอบกลับผิดพลาด ({response.status_code}): {response.text}")


def build_low_stock_message(products: list[Product]) -> str:
    lines = ["แจ้งเตือนสต๊อกใกล้หมด"]
    for p in products:
        lines.append(f"- {p.name} ({p.sku}): เหลือ {p.stock_quantity} (ขั้นต่ำ {p.low_stock_threshold})")
    return "\n".join(lines)
