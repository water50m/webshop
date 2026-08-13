import re
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Ingredient, Product

GREETING_PHRASES = ["สวัสดี", "หวัดดี", "ดีค่ะ", "ดีครับ", "ดีจ้า", "ดีจ้ะ", "hello", "hi", "hey"]

QUESTION_PHRASES = [
    "ไหม",
    "มั้ย",
    "หรือไม่",
    "หรือเปล่า",
    "รึเปล่า",
    "เท่าไหร่",
    "เท่าไร",
    "กี่บาท",
    "กี่โมง",
    "ที่ไหน",
    "ยังไง",
    "อย่างไร",
    "ทำไม",
    "คืออะไร",
    "มีอะไรบ้าง",
]

POLITENESS_PARTICLES = ["ค่ะ", "คะ", "ครับ", "จ้า", "จ้ะ", "จ๊ะ", "นะ", "น้า"]

# Longest phrase first so a window check like "ไม่ใส่" isn't masked by the
# shorter "ไม่" also matching.
NEGATION_MARKERS = ["ไม่ใส่", "ไม่เอา", "ไม่ต้อง", "งดใส่", "งด", "ไม่"]
NEGATION_WINDOW_CHARS = 8


def classify_sentence(text: str) -> str:
    """Classify a single incoming message as "empty", "question", "greeting", or "order".

    Heuristic only (keyword/regex based, no real NLU) -- see order_parser
    limitations discussed with the user for what this does not handle.
    """
    stripped = (text or "").strip()
    if not stripped:
        return "empty"
    if stripped.endswith("?") or stripped.endswith("？"):
        return "question"

    lowered = stripped.lower()
    if any(phrase in lowered for phrase in QUESTION_PHRASES):
        return "question"

    remainder = lowered
    for phrase in GREETING_PHRASES:
        remainder = remainder.replace(phrase, "")
    for particle in POLITENESS_PARTICLES:
        remainder = remainder.replace(particle, "")
    remainder = re.sub(r"[\s.,!~]+", "", remainder)

    return "greeting" if remainder == "" else "order"


def is_order_sentence(text: str) -> bool:
    """Rule 1: not a greeting/question => treat the message as an order."""
    return classify_sentence(text) == "order"


@dataclass
class CatalogTerm:
    kind: str  # "product" | "modifier" | "ingredient"
    id: int
    name: str


@dataclass
class ParsedMatch:
    term: CatalogTerm
    matched_text: str
    negated: bool
    start: int


def _load_catalog_terms(db: Session) -> list[CatalogTerm]:
    terms: list[CatalogTerm] = []
    for product in db.query(Product).all():
        if product.name:
            terms.append(CatalogTerm(kind="product", id=product.id, name=product.name))
        for modifier in product.modifiers:
            if modifier.name:
                terms.append(CatalogTerm(kind="modifier", id=modifier.id, name=modifier.name))
    for ingredient in db.query(Ingredient).all():
        if ingredient.name:
            terms.append(CatalogTerm(kind="ingredient", id=ingredient.id, name=ingredient.name))
    # Scan longer names first so a more specific term (e.g. "ชาไทยเย็น") wins
    # over a shorter one it contains (e.g. "ชาไทย").
    terms.sort(key=lambda t: len(t.name), reverse=True)
    return terms


def _is_negated(text: str, match_start: int) -> bool:
    """Rule 3: look only at the text immediately before this match for a
    negation marker (e.g. "ไม่ใส่ผัก" negates "ผัก")."""
    window_start = max(0, match_start - NEGATION_WINDOW_CHARS)
    preceding = text[window_start:match_start].strip()
    return any(preceding.endswith(marker) for marker in NEGATION_MARKERS)


def parse_order_text(db: Session, text: str) -> list[ParsedMatch]:
    """Rule 2 + 3 + 4: find menu/modifier/ingredient terms mentioned in `text`
    and flag ones immediately preceded by a negation word.

    Only ever looks at the single message passed in -- callers must not feed
    this conversation history, only the message that was just received.
    """
    if not text:
        return []
    lowered = text.lower()

    candidates: list[tuple[int, int, CatalogTerm]] = []
    for term in _load_catalog_terms(db):
        needle = term.name.lower()
        if not needle:
            continue
        start = 0
        while True:
            idx = lowered.find(needle, start)
            if idx == -1:
                break
            candidates.append((idx, idx + len(needle), term))
            start = idx + 1

    # Resolve overlaps: earliest start wins, ties broken by the longer match.
    candidates.sort(key=lambda c: (c[0], -(c[1] - c[0])))
    occupied_until = -1
    matches: list[ParsedMatch] = []
    for start, end, term in candidates:
        if start < occupied_until:
            continue
        matches.append(
            ParsedMatch(term=term, matched_text=text[start:end], negated=_is_negated(text, start), start=start)
        )
        occupied_until = end
    return matches
