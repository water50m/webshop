import json

import httpx
from sqlalchemy.orm import Session

from app.models import Ingredient, Product
from app.services.order_parser import CatalogTerm, ParsedMatch

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODEL = "claude-haiku-4-5-20251001"

PROMPT_TEMPLATE = """คุณคือระบบช่วยตีความข้อความสั่งซื้อจากลูกค้าร้านอาหาร/ร้านค้า
รายการเมนู/ท็อปปิ้ง/วัตถุดิบทั้งหมดในระบบมีดังนี้:
{catalog}

ข้อความจากลูกค้า: "{text}"

ให้ตอบกลับเป็น JSON เท่านั้น ห้ามมีข้อความอื่นปนนอก JSON รูปแบบ:
{{
  "classification": "greeting" | "question" | "order",
  "items": [
    {{"name": "<ชื่อต้องตรงกับรายการด้านบนเป๊ะๆ>", "quantity": <จำนวนเต็ม>, "negated": <true ถ้าลูกค้าปฏิเสธ/ไม่เอา/ไม่ใส่รายการนี้>}}
  ]
}}

กฎ:
- ถ้าข้อความเป็นแค่คำทักทายหรือคำถาม ให้ classification เป็น "greeting" หรือ "question" ตามลำดับ และ items เป็น array ว่าง
- ชื่อใน items ต้องตรงกับชื่อในรายการด้านบนเป๊ะๆ เท่านั้น ห้ามแต่งชื่อใหม่หรือเดาเอง ถ้าไม่แน่ใจว่าตรงกับอะไรให้ข้ามรายการนั้นไป
- ตีความเฉพาะข้อความที่ให้มาเท่านั้น ไม่ต้องอ้างอิงบทสนทนาอื่นที่ไม่ได้ให้มา
"""


class AiOrderParserError(Exception):
    """Raised whenever the AI call can't be trusted -- callers should fall back
    to the algorithmic parser instead of dropping the message."""


def _build_catalog(db: Session) -> tuple[str, dict[str, CatalogTerm]]:
    lookup: dict[str, CatalogTerm] = {}
    lines: list[str] = []
    for product in db.query(Product).all():
        if not product.name:
            continue
        lookup[product.name] = CatalogTerm(kind="product", id=product.id, name=product.name)
        lines.append(f"- เมนู: {product.name}")
        for modifier in product.modifiers:
            if modifier.name:
                lookup[modifier.name] = CatalogTerm(kind="modifier", id=modifier.id, name=modifier.name)
                lines.append(f"  - ท็อปปิ้งของ {product.name}: {modifier.name}")
    for ingredient in db.query(Ingredient).all():
        if ingredient.name:
            lookup[ingredient.name] = CatalogTerm(kind="ingredient", id=ingredient.id, name=ingredient.name)
            lines.append(f"- วัตถุดิบ: {ingredient.name}")
    return "\n".join(lines) or "(ยังไม่มีสินค้าในระบบ)", lookup


def parse_order_with_ai(db: Session, text: str, api_key: str) -> tuple[str, list[ParsedMatch]]:
    """Ask the AI to classify+extract order items from a single message.

    Returns (classification, matches). Raises AiOrderParserError on any
    failure (missing key, network error, bad response, unparseable JSON) --
    callers should catch this and fall back to the algorithmic parser rather
    than silently dropping the customer's message.
    """
    if not api_key:
        raise AiOrderParserError("ยังไม่ได้ตั้งค่า AI API Key ในหน้าตั้งค่า")
    if not text:
        return "empty", []

    catalog_text, lookup = _build_catalog(db)
    prompt = PROMPT_TEMPLATE.format(catalog=catalog_text, text=text)

    try:
        response = httpx.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            },
            json={"model": MODEL, "max_tokens": 1024, "messages": [{"role": "user", "content": prompt}]},
            timeout=15,
        )
    except httpx.HTTPError as exc:
        raise AiOrderParserError(f"เรียก AI API ไม่สำเร็จ: {exc}") from exc

    if response.status_code >= 400:
        raise AiOrderParserError(f"AI API ตอบกลับผิดพลาด ({response.status_code}): {response.text}")

    try:
        body = response.json()
        raw_text = body["content"][0]["text"]
        parsed = json.loads(raw_text)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AiOrderParserError(f"ตีความผลลัพธ์จาก AI ไม่สำเร็จ: {exc}") from exc

    classification = parsed.get("classification", "order")
    matches: list[ParsedMatch] = []
    for position, item in enumerate(parsed.get("items", []) or []):
        term = lookup.get(item.get("name", ""))
        if term is None:
            # AI named something outside the catalog -- skip rather than guess.
            continue
        quantity = max(1, int(item.get("quantity") or 1))
        negated = bool(item.get("negated", False))
        for _ in range(quantity):
            matches.append(ParsedMatch(term=term, matched_text=term.name, negated=negated, start=position))

    return classification, matches
