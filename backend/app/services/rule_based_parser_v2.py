"""Rule-based Parser v2 test engine.

This module is intentionally not imported by live message ingestion.  It
turns one message into a reviewable result and, when a human is needed, stores
only a redacted handoff record for future rule improvements.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime

from pythainlp.tokenize import word_tokenize
from pythainlp.util import Trie
from rapidfuzz import fuzz, process
from sqlalchemy.orm import Session

from app.models import AdminHandoffLog, Conversation, ParserV2ConversationState, Product, ProductAlias
from app.services.history_analysis_preparation import redact_text

THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")
THAI_NUMBER_WORDS = {
    "หนึ่ง": 1,
    "นึง": 1,
    "สอง": 2,
    "สาม": 3,
    "สี่": 4,
    "ห้า": 5,
    "หก": 6,
    "เจ็ด": 7,
    "แปด": 8,
    "เก้า": 9,
    "สิบ": 10,
}
# Questions are intentionally handled by a small, explainable gate.  Anything
# that is not in ANSWERABLE_QUESTION_SIGNALS stops order parsing and goes to an
# admin; we do not need a growing taxonomy of operational questions.
ANSWERABLE_QUESTION_SIGNALS = {
    "ask_price": ("ราคา", "กี่บาท", "เท่าไหร่", "เท่าไร"),
    "ask_menu": ("เมนู", "มีอะไรบ้าง", "เหลืออะไรบ้าง"),
}
GENERIC_QUESTION_SIGNALS = (
    "ไหม",
    "มั้ย",
    "มั๊ย",
    "มัย",
    "หรือ",
    "รึ",
    "เหรอ",
    "หรอ",
    "อะไร",
    "กี่",
    "ที่ไหน",
    "เมื่อไหร่",
    "เมื่อไร",
    "ยังไง",
    "อย่างไร",
    "ไหน",
    "ปะ",
    "เปล่า",
    "ป่าว",
    "?",
    "？",
)
ORDER_SIGNALS = ("เอา", "รับ", "สั่ง", "ขอ")
PAYMENT_SIGNALS = ("โอน", "สลิป", "คนละครึ่ง", "ไทยช่วยไทย", "จ่าย")
COMPLAINT_SIGNALS = ("ออเดอร์ไม่ครบ", "ไม่ครบ", "ส่งผิด", "ผิดหอ", "ผิดที่", "ยังไม่ได้ส่ง")
CUSTOMIZATION_SIGNALS = ("ไม่เอาผัก", "ไม่ใส่", "เอาแต่", "แยกไก่")
# Intentionally a small closed set: these are common stand-alone Thai
# greetings with one omitted/mistyped character. Greeting recovery is safe;
# unlike a product typo it cannot create an order or alter stock.
GREETING_PATTERN = re.compile(
    r"^(?:สวัสดี?|สวัดดี|สวัสดี|สวสดี|หวัดดี?|หวัดด|hello|hi)(?:ครับ|คับ|ค่ะ|คะ|ค้าบ|คร้าบ)?$"
)


@dataclass(frozen=True)
class CatalogEntry:
    product_id: int
    product_name: str
    match_text: str
    source: str


@dataclass(frozen=True)
class ParsedItem:
    product_id: int
    product_name: str
    matched_text: str
    quantity: int
    packaging: str
    match_source: str
    fallback_product_name: str | None = None
    substitution_from: str | None = None


@dataclass(frozen=True)
class ParserV2Result:
    normalized_text: str
    tokens: list[str]
    intent: str
    next_state: str
    items: list[ParsedItem]
    handoff_reason: str | None
    candidates: list[dict]
    order_options: list[str] = field(default_factory=list)
    answer_text: str | None = None


def normalize_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "").translate(THAI_DIGITS).lower()
    normalized = normalized.replace("＋", "+")
    normalized = re.sub(r"\s*\+\s*", " + ", normalized)
    normalized = re.sub(r"(?<=[ก-๙a-z])(?=\d)", " ", normalized)
    normalized = re.sub(r"(?<=\d)(?=[ก-๙a-z])", " ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()


def _contains(normalized_text: str, text: str) -> bool:
    """Compare rule words in the same Unicode-normalized form as customer text."""
    return normalize_text(text) in normalized_text


def _catalog(db: Session) -> list[CatalogEntry]:
    entries = [
        CatalogEntry(product_id=product.id, product_name=product.name, match_text=normalize_text(product.name), source="exact")
        for product in db.query(Product).all()
        if product.name
    ]
    aliases = db.query(ProductAlias).filter(ProductAlias.status == "approved").all()
    entries.extend(
        CatalogEntry(
            product_id=alias.product_id,
            product_name=alias.product.name,
            match_text=normalize_text(alias.alias_text),
            source="alias",
        )
        for alias in aliases
        if alias.alias_text
    )
    return sorted(entries, key=lambda entry: len(entry.match_text), reverse=True)


def _tokens(normalized_text: str, entries: list[CatalogEntry]) -> list[str]:
    dictionary = Trie([entry.match_text for entry in entries])
    return [token for token in word_tokenize(normalized_text, custom_dict=dictionary, engine="newmm", keep_whitespace=False) if token.strip()]


def _available_products(db: Session, predicate) -> list[Product]:
    return [
        product
        for product in db.query(Product).order_by(Product.name).all()
        if product.is_available and (product.stock_mode == "unlimited" or product.stock_quantity > 0) and predicate(product)
    ]


def _names(products: list[Product]) -> str:
    return ", ".join(product.name for product in products)


def _question_result(
    db: Session, normalized_text: str, matches: list[tuple[int, int, CatalogEntry]]
) -> tuple[str, str, str | None, str | None] | None:
    """Return (intent, next_state, handoff_reason, answer_text) for a question.

    Stock-backed answers are permitted only for positive stock.  A zero stock
    count is deliberately treated as unknown/unavailable and is sent to an
    admin rather than answered optimistically.
    """
    has_known_product = bool(matches)
    has_question_marker = any(_contains(normalized_text, signal) for signal in GENERIC_QUESTION_SIGNALS)
    if _contains(normalized_text, "น้ำจิ้ม") and has_question_marker:
        sauce = db.query(Product).filter(Product.name == "น้ำจิ้ม").first()
        is_available = sauce is not None and sauce.is_available and (
            sauce.stock_mode == "unlimited" or sauce.stock_quantity > 0
        )
        if is_available:
            return "ask_option", "answer_if_verified", None, "สามารถเพิ่มน้ำจิ้มได้ครับ"
        return "ask_admin", "waiting_for_admin", "stock_unavailable_or_unset", None
    if _contains(normalized_text, "น้ำ") and _contains(normalized_text, "อะไร"):
        drinks = _available_products(db, lambda product: product.category == "เครื่องดื่ม" or "น้ำ" in product.name)
        if drinks:
            return "ask_menu", "answer_if_verified", None, f"ขณะนี้มี: {_names(drinks)}"
        return "ask_admin", "waiting_for_admin", "stock_unavailable_or_unset", None
    if has_question_marker and has_known_product and (
        any(_contains(normalized_text, signal) for signal in ("ยังมี", "มีอยู่", "เหลือ", "หมด"))
        or (
            "มี" in normalized_text
            and "ไม่มี" not in normalized_text
            and any(_contains(normalized_text, marker) for marker in ("ไหม", "มั้ย", "มั๊ย", "มัย", "หรอ", "เหรอ", "?"))
        )
    ):
        product_ids = {entry.product_id for _, _, entry in matches}
        products = db.query(Product).filter(Product.id.in_(product_ids)).order_by(Product.name).all()
        available = all(
            product.is_available and (product.stock_mode == "unlimited" or product.stock_quantity > 0)
            for product in products
        )
        if available:
            return "ask_availability", "answer_if_verified", None, f"ขณะนี้มี{_names(products)}ครับ"
        return "ask_admin", "waiting_for_admin", "stock_unavailable_or_unset", None
    if has_question_marker and _contains(normalized_text, "ไก่") and any(
        _contains(normalized_text, word) for word in ("เพิ่ม", "เลือก", "ส่วน")
    ):
        chicken_parts = _available_products(db, lambda product: product.category == "ไก่")
        if chicken_parts:
            return "ask_option", "answer_if_verified", None, f"สามารถเลือกเพิ่มได้: {_names(chicken_parts)}"
        return "ask_admin", "waiting_for_admin", "stock_unavailable_or_unset", None
    if any(signal in normalized_text for signal in ANSWERABLE_QUESTION_SIGNALS["ask_price"]):
        if has_known_product:
            product_ids = {entry.product_id for _, _, entry in matches}
            products = db.query(Product).filter(Product.id.in_(product_ids)).order_by(Product.name).all()
            answer = ", ".join(f"{product.name} {float(product.price):.0f} บาท" for product in products)
            return "ask_price", "answer_if_verified", None, answer
        return "ask_admin", "waiting_for_admin", "question_requires_admin", None
    if any(signal in normalized_text for signal in ANSWERABLE_QUESTION_SIGNALS["ask_menu"]):
        # Order options (for example sauce) can be offered when explicitly
        # requested, but are not stand-alone menu entries.
        menu = _available_products(
            db, lambda product: product.category != "ตัวเลือกออเดอร์" and product.show_in_menu_answer
        )
        if menu:
            return "ask_menu", "answer_if_verified", None, f"ขณะนี้มี: {_names(menu)}"
        return "ask_admin", "waiting_for_admin", "stock_unavailable_or_unset", None
    if any(signal in normalized_text for signal in GENERIC_QUESTION_SIGNALS):
        return "ask_admin", "waiting_for_admin", "question_requires_admin", None
    return None


def _operational_handoff_reason(normalized_text: str) -> str | None:
    """Block operational instructions that Parser v2 cannot execute safely yet."""
    if any(_contains(normalized_text, signal) for signal in COMPLAINT_SIGNALS):
        return "complaint_requires_admin"
    if any(_contains(normalized_text, signal) for signal in ("โอนไม่ได้", "อีกสลิป", "สลิปไม่เข้า")):
        return "payment_issue_requires_admin"
    if any(_contains(normalized_text, signal) for signal in ("แยกกันจ่าย", "จ่ายแยก")) or (
        _contains(normalized_text, "แยกเป็น") and (_contains(normalized_text, "จ่าย") or _contains(normalized_text, "บิล"))
    ):
        return "split_payment_requires_admin"
    if any(_contains(normalized_text, signal) for signal in ("ส่งที่เดิม", "ที่เดิม")):
        return "delivery_context_requires_admin"
    if any(_contains(normalized_text, signal) for signal in CUSTOMIZATION_SIGNALS):
        return "customization_requires_admin"
    substitution_condition = re.search(r"ถ้า\s*(ไก่ทอด|ไก่ต้ม)\s*หมด.*?(?:เอา|รับ)?\s*(ไก่ทอด|ไก่ต้ม)\s*แทน", normalized_text)
    if _contains(normalized_text, "แทน") and substitution_condition is None:
        return "replacement_context_requires_admin"
    return None


def _greeting_result(normalized_text: str) -> tuple[str, str, str | None, str | None] | None:
    if GREETING_PATTERN.fullmatch(normalized_text):
        return "greeting", "awaiting_order", None, "สวัสดีครับ รับอะไรดีครับ"
    return None


def _ambiguous_special_order_result(db: Session, normalized_text: str) -> ParserV2Result | None:
    """Ask before interpreting a bare 'พิเศษ' as either rice or chicken.

    The product catalog may contain both kinds (and several chicken
    preparations), so choosing one automatically would create the wrong order.
    """
    if "พิเศษ" not in normalized_text or not any(signal in normalized_text for signal in ORDER_SIGNALS):
        return None
    if "ข้าว" in normalized_text or "ไก่" in normalized_text:
        return None
    candidates = [
        product
        for product in _available_products(db, lambda product: "พิเศษ" in product.name)
        if "ข้าว" in product.name or "ไก่" in product.name
    ]
    if not any("ข้าว" in product.name for product in candidates) or not any("ไก่" in product.name for product in candidates):
        return None
    quantity_match = re.search(r"(?<!\d)(\d{1,3})(?!\d)", normalized_text)
    quantity = int(quantity_match.group(1)) if quantity_match else 1
    return ParserV2Result(
        normalized_text,
        [],
        "ask_special_type",
        "awaiting_special_type",
        [],
        None,
        [
            {"product_id": product.id, "product_name": product.name, "quantity": quantity}
            for product in candidates
        ],
        answer_text="รับพิเศษเป็นข้าวหรือไก่ครับ",
    )


def _matches(normalized_text: str, entries: list[CatalogEntry]) -> list[tuple[int, int, CatalogEntry]]:
    candidates: list[tuple[int, int, CatalogEntry]] = []
    for entry in entries:
        start = 0
        while True:
            index = normalized_text.find(entry.match_text, start)
            if index < 0:
                break
            candidates.append((index, index + len(entry.match_text), entry))
            start = index + 1
    candidates.sort(key=lambda candidate: (candidate[0], -(candidate[1] - candidate[0])))
    selected: list[tuple[int, int, CatalogEntry]] = []
    occupied_until = -1
    for candidate in candidates:
        if candidate[0] < occupied_until:
            continue
        selected.append(candidate)
        occupied_until = candidate[1]
    return selected


def _match_is_negated(text: str, start: int) -> bool:
    """True when the menu occurrence is directly preceded by a refusal.

    This deliberately applies only to a short prefix so an earlier phrase such
    as ``ไม่เอา... แล้วเอา...`` cannot cancel a later real order.
    """
    prefix = text[max(0, start - 12) : start]
    return bool(re.search(r"(?:ไม่เอา|ไม่รับ|ไม่สั่ง|งด)\s*$", prefix))


def _quantity(text: str, start: int, end: int) -> int:
    """Return the closest explicit amount to this product mention."""
    window_start = max(0, start - 16)
    window_end = min(len(text), end + 16)
    numeric_candidates: list[tuple[int, int]] = []
    for numeric in re.finditer(r"(?<!\d)(\d{1,3})(?!\d)", text[window_start:window_end]):
        numeric_start = window_start + numeric.start()
        numeric_end = window_start + numeric.end()
        distance = start - numeric_end if numeric_end <= start else numeric_start - end
        numeric_candidates.append((max(0, distance), int(numeric.group(1))))
    if numeric_candidates:
        return max(1, min(numeric_candidates, key=lambda candidate: candidate[0])[1])
    nearby = f"{text[window_start:start]} {text[end:window_end]}"
    for word, value in THAI_NUMBER_WORDS.items():
        if word in nearby:
            return value
    return 1


def _addition_quantity(text: str, marker_index: int, start: int, end: int) -> int:
    """Amounts in an added item never inherit an earlier order item's amount."""
    addition_start = marker_index + len("เพิ่ม")
    candidates: list[tuple[int, int]] = []
    for numeric in re.finditer(r"(?<!\d)(\d{1,3})(?!\d)", text[addition_start : min(len(text), end + 10)]):
        numeric_start = addition_start + numeric.start()
        numeric_end = addition_start + numeric.end()
        distance = start - numeric_end if numeric_end <= start else numeric_start - end
        candidates.append((max(0, distance), int(numeric.group(1))))
    return max(1, min(candidates, key=lambda candidate: candidate[0])[1]) if candidates else 1


def _fuzzy_candidates(normalized_text: str, tokens: list[str], entries: list[CatalogEntry]) -> list[dict]:
    choices = {entry.match_text: entry for entry in entries}
    queries = [token for token in tokens if len(token) >= 3] or [normalized_text]
    results: list[dict] = []
    for query in queries:
        for matched_text, score, _ in process.extract(query, choices.keys(), scorer=fuzz.ratio, limit=2):
            entry = choices[matched_text]
            candidate = {
                "matched_text": query,
                "product_id": entry.product_id,
                "product_name": entry.product_name,
                "score": round(float(score), 2),
            }
            if candidate not in results:
                results.append(candidate)
    return sorted(results, key=lambda candidate: candidate["score"], reverse=True)[:2]


def _stock_candidates(db: Session, product_ids: set[int]) -> tuple[list[Product], list[Product]]:
    products = db.query(Product).filter(Product.id.in_(product_ids)).all() if product_ids else []
    return products, [product for product in products if product.stock_quantity <= 0]


def _unresolved_addition(
    db: Session, normalized_text: str, matches: list[tuple[int, int, CatalogEntry]], entries: list[CatalogEntry]
) -> tuple[str, list[dict]] | None:
    """Safely handle an unmatched phrase following 'เพิ่ม'.

    An exact product is already present in ``matches``.  For an incomplete
    addition such as 'เพิ่มไก่', do not invent a menu item: report stock-zero
    candidates as unavailable, otherwise ask an admin to disambiguate.
    """
    marker_index = normalized_text.rfind("เพิ่ม")
    if marker_index < 0 or _contains(normalized_text[marker_index:], "น้ำจิ้ม"):
        return None
    suffix = normalized_text[marker_index + len("เพิ่ม") :].strip(" ,.+")
    # In "ขอน้ำจิ้มเพิ่มด้วยครับ" the word before "เพิ่ม" is already a
    # matched product.  The remaining words are only polite/trailing language,
    # not the name of another item.  Do not turn that safe, explicit request
    # into an invented addition.
    trailing_particles = ("ด้วย", "หน่อย", "นะ", "ครับ", "ค่ะ", "คะ", "จ้า")
    if any(end <= marker_index for _, end, _ in matches) and any(suffix.startswith(particle) for particle in trailing_particles):
        return None
    if not suffix:
        return "addition_requires_confirmation", []
    if any(start >= marker_index for start, _, _ in matches):
        return None
    related_entries = [entry for entry in entries if len(suffix) >= 2 and suffix in entry.match_text]
    product_ids = {entry.product_id for entry in related_entries}
    products, _ = _stock_candidates(db, product_ids)
    unavailable = [
        product for product in products if not product.is_available or (product.stock_mode != "unlimited" and product.stock_quantity <= 0)
    ]
    candidates = [
        {
            "matched_text": suffix,
            "product_id": product.id,
            "product_name": product.name,
            "score": 100.0,
        }
        for product in products
    ]
    if not products or unavailable:
        return "stock_unavailable_or_unset", candidates
    return "addition_requires_confirmation", candidates


def _contextual_chicken_addition(
    normalized_text: str, matches: list[tuple[int, int, CatalogEntry]], entries: list[CatalogEntry]
) -> tuple[int, int, CatalogEntry, int] | None:
    """Resolve an abbreviated chicken part from the cooking method already ordered.

    ``เพิ่มน่อง`` is safe to resolve only when the customer has already
    selected exactly one preparation in this same message: ``ทอด`` or ``ต้ม``.
    It deliberately does not infer from ``ไก่ผสม`` or from an order containing
    both methods.  The added part defaults to one unless it has its own amount.
    """
    marker_index = normalized_text.rfind("เพิ่ม")
    if marker_index < 0 or any(start >= marker_index for start, _, _ in matches):
        return None
    suffix = normalized_text[marker_index + len("เพิ่ม") :].strip(" ,.+")
    part_match = re.match(r"(น่อง|ปีก)(?:ไก่)?(?:\s*(\d{1,3}))?", suffix)
    if part_match is None:
        return None
    preparations = {
        preparation
        for _, _, entry in matches
        for preparation in ("ทอด", "ต้ม")
        if preparation in entry.product_name
    }
    if len(preparations) != 1:
        return None
    target_name = f"{part_match.group(1)}ไก่{preparations.pop()}"
    target_entry = next(
        (entry for entry in entries if entry.product_name == target_name and entry.source == "exact"),
        None,
    )
    if target_entry is None:
        return None
    part_start = marker_index + len("เพิ่ม") + normalized_text[marker_index + len("เพิ่ม") :].find(part_match.group(1))
    part_end = part_start + len(part_match.group(0))
    quantity = int(part_match.group(2)) if part_match.group(2) else 1
    return part_start, part_end, target_entry, quantity


def _conditional_substitution(
    normalized_text: str, matches: list[tuple[int, int, CatalogEntry]], entries: list[CatalogEntry]
) -> tuple[list[tuple[int, int, CatalogEntry]], dict[int, CatalogEntry]]:
    """Extract a verified 'if sold out, replace with' instruction.

    The wording is accepted only for an explicit fried/boiled chicken swap and
    only when that swap maps the ordered catalog item to another real catalog
    item.  Words inside the condition are not extra order lines.
    """
    condition = re.search(r"ถ้า\s*(ไก่ทอด|ไก่ต้ม)\s*หมด.*?(?:เอา|รับ)?\s*(ไก่ทอด|ไก่ต้ม)\s*แทน", normalized_text)
    if condition is None or condition.group(1) == condition.group(2):
        return matches, {}
    condition_start = condition.start()
    source_phrase, target_phrase = condition.group(1), condition.group(2)
    main_matches = [match for match in matches if match[0] < condition_start]
    fallback_by_product: dict[int, CatalogEntry] = {}
    for _, _, entry in main_matches:
        if source_phrase not in entry.product_name:
            continue
        fallback_name = entry.product_name.replace(source_phrase, target_phrase)
        fallback = next(
            (candidate for candidate in entries if candidate.product_name == fallback_name and candidate.source == "exact"),
            None,
        )
        if fallback is not None:
            fallback_by_product[entry.product_id] = fallback
    return (main_matches, fallback_by_product) if fallback_by_product else (matches, {})


def parse_message(db: Session, text: str, *, entries: list[CatalogEntry] | None = None) -> ParserV2Result:
    """Parse one message without creating an order or modifying live conversations."""
    normalized = normalize_text(text)
    entries = entries if entries is not None else _catalog(db)
    tokens = _tokens(normalized, entries)
    raw_matches = _matches(normalized, entries)
    negated_matches = [match for match in raw_matches if _match_is_negated(normalized, match[0])]
    matches = [match for match in raw_matches if not _match_is_negated(normalized, match[0])]
    if negated_matches and not matches:
        return ParserV2Result(normalized, tokens, "ask_admin", "waiting_for_admin", [], "negated_product_without_order", [])
    operational_handoff = _operational_handoff_reason(normalized)
    if operational_handoff:
        return ParserV2Result(normalized, tokens, "ask_admin", "waiting_for_admin", [], operational_handoff, [])
    greeting = _greeting_result(normalized)
    if greeting:
        intent, next_state, handoff_reason, answer_text = greeting
        return ParserV2Result(normalized, tokens, intent, next_state, [], handoff_reason, [], answer_text=answer_text)
    question = _question_result(db, normalized, matches)
    if question:
        intent, next_state, handoff_reason, answer_text = question
        return ParserV2Result(
            normalized, tokens, intent, next_state, [], handoff_reason, [], answer_text=answer_text
        )
    ambiguous_special = _ambiguous_special_order_result(db, normalized)
    if ambiguous_special:
        return ambiguous_special

    if matches:
        matches, fallback_by_product = _conditional_substitution(normalized, matches, entries)
        contextual_addition = _contextual_chicken_addition(normalized, matches, entries)
        quantity_overrides: dict[tuple[int, int, int], int] = {}
        if contextual_addition is not None:
            addition_start, addition_end, addition_entry, addition_quantity = contextual_addition
            matches.append((addition_start, addition_end, addition_entry))
            quantity_overrides[(addition_start, addition_end, addition_entry.product_id)] = addition_quantity

        addition_marker = normalized.rfind("เพิ่ม")

        def quantity_for_match(start: int, end: int, entry: CatalogEntry) -> int:
            override = quantity_overrides.get((start, end, entry.product_id))
            if override is not None:
                return override
            if addition_marker >= 0 and start >= addition_marker + len("เพิ่ม"):
                return _addition_quantity(normalized, addition_marker, start, end)
            return _quantity(normalized, start, end)

        product_ids = {entry.product_id for _, _, entry in matches} | {entry.product_id for entry in fallback_by_product.values()}
        catalog_products, _ = _stock_candidates(db, product_ids)
        products_by_id = {product.id: product for product in catalog_products}
        effective_matches: list[tuple[int, int, CatalogEntry]] = []
        fallback_names: dict[tuple[int, int, int], str] = {}
        substitution_sources: dict[tuple[int, int, int], str] = {}
        for start, end, entry in matches:
            product = products_by_id[entry.product_id]
            requested_quantity = quantity_for_match(start, end, entry)
            fallback = fallback_by_product.get(entry.product_id)
            source_unavailable = not product.is_available or (
                product.stock_mode != "unlimited" and product.stock_quantity < requested_quantity
            )
            if source_unavailable and fallback is not None:
                fallback_product = products_by_id[fallback.product_id]
                fallback_available = fallback_product.is_available and (
                    fallback_product.stock_mode == "unlimited" or fallback_product.stock_quantity >= requested_quantity
                )
                if fallback_available:
                    effective_matches.append((start, end, fallback))
                    substitution_sources[(start, end, fallback.product_id)] = entry.product_name
                    continue
            effective_matches.append((start, end, entry))
            if fallback is not None:
                fallback_names[(start, end, entry.product_id)] = fallback.product_name
        matches = effective_matches
        matched_products = [products_by_id[entry.product_id] for _, _, entry in matches]
        requested_quantity_by_product: dict[int, int] = {}
        for start, end, entry in matches:
            requested_quantity_by_product[entry.product_id] = requested_quantity_by_product.get(entry.product_id, 0) + quantity_for_match(start, end, entry)
        unavailable_products = [
            product
            for product in matched_products
            if not product.is_available
            or (product.stock_mode != "unlimited" and product.stock_quantity < requested_quantity_by_product.get(product.id, 0))
        ]
        if unavailable_products:
            candidates = [
                {
                    "matched_text": product.name,
                    "product_id": product.id,
                    "product_name": product.name,
                    "score": 100.0,
                    "requested_quantity": requested_quantity_by_product.get(product.id, 0),
                    "available_quantity": product.stock_quantity,
                }
                for product in unavailable_products
            ]
            return ParserV2Result(
                normalized, tokens, "start_order", "waiting_for_admin", [], "stock_unavailable_or_unset", candidates
            )
        unresolved_addition = _unresolved_addition(db, normalized, matches, entries)
        if unresolved_addition:
            reason, candidates = unresolved_addition
            return ParserV2Result(normalized, tokens, "start_order", "waiting_for_admin", [], reason, candidates)
        packaging = "box" if "กล่อง" in normalized else "wrapped"
        items = [
            ParsedItem(
                product_id=entry.product_id,
                product_name=entry.product_name,
                matched_text=normalized[start:end],
                quantity=quantity_for_match(start, end, entry),
                packaging=packaging,
                match_source=entry.source,
                fallback_product_name=fallback_names.get((start, end, entry.product_id)),
                substitution_from=substitution_sources.get((start, end, entry.product_id)),
            )
            for start, end, entry in matches
        ]
        if any(signal in normalized for signal in PAYMENT_SIGNALS):
            return ParserV2Result(normalized, tokens, "payment", "waiting_for_confirmation", items, None, [])
        return ParserV2Result(normalized, tokens, "start_order", "collecting_delivery_details", items, None, [])

    fuzzy_candidates = _fuzzy_candidates(normalized, tokens, entries)
    looks_like_order = any(signal in normalized for signal in ORDER_SIGNALS)
    if fuzzy_candidates and fuzzy_candidates[0]["score"] >= 92:
        margin = fuzzy_candidates[0]["score"] - (fuzzy_candidates[1]["score"] if len(fuzzy_candidates) > 1 else 0)
        if margin >= 8:
            return ParserV2Result(
                normalized, tokens, "start_order", "waiting_for_admin", [], "fuzzy_match_requires_confirmation", fuzzy_candidates
            )
    if looks_like_order:
        return ParserV2Result(normalized, tokens, "start_order", "waiting_for_admin", [], "unmatched_product", fuzzy_candidates)
    if any(signal in normalized for signal in PAYMENT_SIGNALS):
        return ParserV2Result(normalized, tokens, "payment", "waiting_for_admin", [], "unlinked_payment", [])
    return ParserV2Result(normalized, tokens, "unknown", "waiting_for_admin", [], "unknown_message", fuzzy_candidates)


def _context_reference_result(db: Session, text: str, state: ParserV2ConversationState) -> ParserV2Result | None:
    """Resolve only unambiguous references to the most recent single item."""
    normalized = normalize_text(text)
    refers_to_last_item = any(phrase in normalized for phrase in ("เอาอันนั้น", "เอาอันเดิม", "เอาแบบเดิม", "เอาเหมือนเดิม"))
    if not refers_to_last_item:
        return None
    if len(state.last_items) != 1:
        return ParserV2Result(normalized, [], "ask_admin", "waiting_for_admin", [], "context_reference_requires_admin", [])
    previous = state.last_items[0]
    amount = re.search(r"(?<!\d)(\d{1,3})(?!\d)", normalized)
    quantity = int(amount.group(1)) if amount else 1
    product = db.get(Product, previous.get("product_id"))
    if product is None or not product.is_available or (
        product.stock_mode != "unlimited" and product.stock_quantity < quantity
    ):
        return ParserV2Result(normalized, [], "ask_admin", "waiting_for_admin", [], "stock_unavailable_or_unset", [])
    packaging = "box" if "กล่อง" in normalized else previous.get("packaging", "wrapped")
    item = ParsedItem(
        product_id=product.id,
        product_name=product.name,
        matched_text=normalized,
        quantity=quantity,
        packaging=packaging,
        match_source="context",
    )
    return ParserV2Result(normalized, [], "start_order", "collecting_delivery_details", [item], None, [])


def _pending_special_choice_result(
    db: Session, text: str, state: ParserV2ConversationState
) -> ParserV2Result | None:
    """Turn a reply to the bare-special question into a verified item."""
    if state.state != "awaiting_special_type" or not state.last_items:
        return None
    pending = state.last_items[0]
    candidate_ids = pending.get("pending_special_candidate_ids")
    if not isinstance(candidate_ids, list):
        return None
    normalized = normalize_text(text)
    requested_kind = "ข้าว" if "ข้าว" in normalized else "ไก่" if "ไก่" in normalized else None
    if requested_kind is None:
        return ParserV2Result(
            normalized, [], "ask_special_type", "awaiting_special_type", [], None, [],
            answer_text="กรุณาเลือกพิเศษเป็นข้าวหรือไก่ครับ",
        )
    candidates = [
        product
        for product in db.query(Product).filter(Product.id.in_(candidate_ids)).order_by(Product.name).all()
        if requested_kind in product.name
        and product.is_available
        and (product.stock_mode == "unlimited" or product.stock_quantity > 0)
    ]
    quantity = max(1, int(pending.get("quantity", 1)))
    if len(candidates) != 1:
        options = ", ".join(product.name for product in candidates)
        answer = f"รับไก่พิเศษแบบไหนครับ: {options}" if options else "ขออภัย ขณะนี้ไม่มีรายการพิเศษที่เลือกได้ครับ"
        return ParserV2Result(normalized, [], "ask_special_type", "awaiting_special_type", [], None, [], answer_text=answer)
    product = candidates[0]
    if product.stock_mode != "unlimited" and product.stock_quantity < quantity:
        return ParserV2Result(normalized, [], "ask_admin", "waiting_for_admin", [], "stock_unavailable_or_unset", [])
    return ParserV2Result(
        normalized,
        [],
        "start_order",
        "collecting_delivery_details",
        [ParsedItem(product.id, product.name, normalized, quantity, "wrapped", "special_choice")],
        None,
        [],
    )


def get_or_create_conversation_state(db: Session, conversation_id: int) -> ParserV2ConversationState:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        raise ValueError("ไม่พบบทสนทนา")
    state = db.query(ParserV2ConversationState).filter_by(conversation_id=conversation_id).first()
    if state is None:
        state = ParserV2ConversationState(conversation_id=conversation_id)
        db.add(state)
        db.flush()
    return state


def advance_conversation_state(
    db: Session, conversation_id: int, text: str
) -> tuple[ParserV2Result, ParserV2ConversationState]:
    """Advance Parser v2 memory without sending a reply or creating an order."""
    state = get_or_create_conversation_state(db, conversation_id)
    result = parse_message(db, text)
    special_choice = _pending_special_choice_result(db, text, state)
    contextual = _context_reference_result(db, text, state) if special_choice is None else None
    if special_choice is not None:
        result = special_choice
    if contextual is not None:
        result = contextual
    elif result.handoff_reason == "delivery_context_requires_admin" and state.delivery_context_confirmed:
        result = ParserV2Result(
            normalize_text(text), [], "delivery_reference", "waiting_for_confirmation", [], None, [],
            answer_text="รับทราบ ใช้จุดส่งเดิมที่ยืนยันแล้วครับ",
        )

    if result.items:
        state.last_items = [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "quantity": item.quantity,
                "packaging": item.packaging,
            }
            for item in result.items
        ]
    elif result.intent == "ask_special_type" and result.next_state == "awaiting_special_type":
        candidate_ids = [candidate["product_id"] for candidate in result.candidates if candidate.get("product_id")]
        quantity = next((candidate.get("quantity", 1) for candidate in result.candidates if candidate.get("quantity")), 1)
        if candidate_ids:
            state.last_items = [{"pending_special_candidate_ids": candidate_ids, "quantity": quantity}]
    if result.next_state == "answer_if_verified" and state.state == "awaiting_order":
        pass
    else:
        state.state = result.next_state
    db.flush()
    return result, state


def record_handoff(db: Session, text: str, result: ParserV2Result) -> AdminHandoffLog | None:
    if result.handoff_reason is None:
        return None
    redacted, _ = redact_text(text)
    log = AdminHandoffLog(
        redacted_text=redacted,
        intent=result.intent,
        reason=result.handoff_reason,
        candidates={"items": result.candidates},
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def resolve_handoff(db: Session, handoff: AdminHandoffLog, resolution: str, user_id: int) -> AdminHandoffLog:
    redacted_resolution, _ = redact_text(resolution)
    handoff.status = "resolved"
    handoff.resolution = redacted_resolution
    handoff.resolved_by_user_id = user_id
    handoff.resolved_at = datetime.utcnow()
    db.commit()
    db.refresh(handoff)
    return handoff


def serialize_result(result: ParserV2Result) -> dict:
    return {
        "normalized_text": result.normalized_text,
        "tokens": result.tokens,
        "intent": result.intent,
        "next_state": result.next_state,
        "items": [asdict(item) for item in result.items],
        "handoff_reason": result.handoff_reason,
        "candidates": result.candidates,
        "order_options": result.order_options,
        "answer_text": result.answer_text,
    }
