import os

os.environ["DATABASE_URL"] = "sqlite:///./test_rule_based_parser_v2.db"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import (
    AdminHandoffLog,
    Channel,
    ChannelType,
    Conversation,
    Customer,
    Product,
    ProductAlias,
    StockMovement,
    User,
    UserRole,
)
from app.services.auth import hash_password
from app.services.rule_based_parser_v2 import advance_conversation_state, parse_message

client = TestClient(app)


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    owner = User(username="owner", password_hash=hash_password("ownerpass"), display_name="Owner", role=UserRole.owner)
    db.add(owner)
    db.add_all(
        [
            Product(sku="SET-FRIED", name="ข้าวหมกไก่ทอด", category="อาหารชุด", price=45, stock_quantity=10),
            Product(sku="SET-BOILED", name="ข้าวหมกไก่ต้ม", category="อาหารชุด", price=45, stock_quantity=10),
            Product(sku="SET-MIXED", name="ข้าวหมกไก่ผสม", category="อาหารชุด", price=60, stock_quantity=10),
            Product(sku="DRUM-FRIED", name="น่องไก่ทอด", category="ไก่", price=15, stock_quantity=10),
            Product(sku="DRUM-BOILED", name="น่องไก่ต้ม", category="ไก่", price=15, stock_quantity=10),
            Product(sku="WING-FRIED", name="ปีกไก่ทอด", category="ไก่", price=15, stock_quantity=10),
            Product(sku="WING-BOILED", name="ปีกไก่ต้ม", category="ไก่", price=15, stock_quantity=10),
            Product(sku="ORDER-OPTION-SAUCE", name="น้ำจิ้ม", category="ตัวเลือกออเดอร์", price=0, stock_mode="unlimited"),
        ]
    )
    db.commit()
    mixed = db.query(Product).filter(Product.sku == "SET-MIXED").one()
    db.add(ProductAlias(product_id=mixed.id, alias_text="ไก่ผสม", status="approved"))
    db.commit()
    db.close()
    login = client.post("/api/auth/login", json={"username": "owner", "password": "ownerpass"})
    assert login.status_code == 200, login.text
    yield
    Base.metadata.drop_all(bind=engine)


def test_normalization_quantity_and_packaging_match_owner_defined_set():
    db = SessionLocal()
    result = parse_message(db, "ขอ ข้าวหมกไก่ทอด ๒ กล่อง")
    db.close()

    assert result.intent == "start_order"
    assert result.next_state == "collecting_delivery_details"
    assert [(item.product_name, item.quantity, item.packaging) for item in result.items] == [
        ("ข้าวหมกไก่ทอด", 2, "box")
    ]


def test_owner_approved_alias_matches_but_unapproved_discovery_never_becomes_order():
    db = SessionLocal()
    result = parse_message(db, "เอาไก่ผสม 1 ห่อ")
    unknown = parse_message(db, "เอาน้ำส้ม 1 ขวด")
    db.close()

    assert [(item.product_name, item.match_source) for item in result.items] == [("ข้าวหมกไก่ผสม", "alias")]
    assert unknown.items == []
    assert unknown.next_state == "waiting_for_admin"
    assert unknown.handoff_reason == "unmatched_product"


def test_negated_product_is_never_added_to_an_order():
    db = SessionLocal()
    result = parse_message(db, "ไม่เอาข้าวหมกไก่ทอด")
    db.close()

    assert result.items == []
    assert result.next_state == "waiting_for_admin"
    assert result.handoff_reason == "negated_product_without_order"


def test_question_has_priority_over_order_and_never_creates_item():
    db = SessionLocal()
    result = parse_message(db, "ข้าวหมกไก่ทอดราคาเท่าไหร่")
    db.close()

    assert result.intent == "ask_price"
    assert result.next_state == "answer_if_verified"
    assert result.items == []


def test_availability_question_has_priority_even_when_it_also_contains_an_order():
    db = SessionLocal()
    db.query(Product).update({"stock_quantity": 0})
    db.commit()
    result = parse_message(db, "ไก่ทอดเหลือไหมครับ เอาข้าวหมกไก่ต้ม 1")
    db.close()

    assert result.intent == "ask_admin"
    assert result.next_state == "waiting_for_admin"
    assert result.handoff_reason == "stock_unavailable_or_unset"
    assert result.items == []


@pytest.mark.parametrize("text", ["ร้านเปิดกี่โมงหรอ", "ส่งที่ไหนครับ"])
def test_generic_question_gate_sends_any_non_answerable_question_to_admin(text):
    db = SessionLocal()
    result = parse_message(db, text)
    db.close()

    assert result.intent == "ask_admin"
    assert result.next_state == "waiting_for_admin"
    assert result.handoff_reason == "question_requires_admin"
    assert result.items == []


def test_stock_backed_menu_and_chicken_answers_only_include_products_with_positive_stock():
    db = SessionLocal()
    db.query(Product).update({"stock_quantity": 0})
    db.query(Product).filter(Product.sku == "DRUM-FRIED").update({"stock_quantity": 3})
    db.query(Product).filter(Product.sku == "WING-FRIED").update({"stock_quantity": 2})
    db.commit()

    chicken = parse_message(db, "เลือกส่วนไก่ได้ไหม")
    menu = parse_message(db, "มีเมนูอะไรบ้าง")
    db.close()

    assert chicken.intent == "ask_option"
    assert chicken.answer_text == "สามารถเลือกเพิ่มได้: น่องไก่ทอด, ปีกไก่ทอด"
    assert menu.intent == "ask_menu"
    assert menu.answer_text == "ขณะนี้มี: น่องไก่ทอด, ปีกไก่ทอด"


def test_sauce_is_unlimited_until_an_admin_marks_it_unavailable():
    db = SessionLocal()
    available = parse_message(db, "ขอน้ำจิ้มเพิ่มได้ไหม")
    sauce = db.query(Product).filter(Product.name == "น้ำจิ้ม").one()
    sauce.is_available = False
    db.commit()
    unavailable = parse_message(db, "ขอน้ำจิ้มเพิ่มได้ไหม")
    db.close()

    assert available.intent == "ask_option"
    assert available.answer_text == "สามารถเพิ่มน้ำจิ้มได้ครับ"
    assert unavailable.intent == "ask_admin"
    assert unavailable.handoff_reason == "stock_unavailable_or_unset"


def test_sauce_in_an_order_is_a_normal_unlimited_product_not_a_question():
    db = SessionLocal()
    result = parse_message(db, "เอาข้าวหมกไก่ทอด 2 กล่อง เพิ่มน้ำจิ้ม")
    db.close()

    assert result.intent == "start_order"
    assert result.next_state == "collecting_delivery_details"
    assert [(item.product_name, item.quantity, item.packaging) for item in result.items] == [
        ("ข้าวหมกไก่ทอด", 2, "box"),
        ("น้ำจิ้ม", 1, "box"),
    ]
    assert result.order_options == []
    assert result.answer_text is None


def test_explicit_sauce_with_a_trailing_addition_particle_is_not_treated_as_an_unknown_item():
    db = SessionLocal()
    result = parse_message(db, "ขอน้ำจิ้มเพิ่มด้วยครับ")
    db.close()

    assert result.next_state == "collecting_delivery_details"
    assert [(item.product_name, item.quantity) for item in result.items] == [("น้ำจิ้ม", 1)]


def test_each_added_item_uses_its_own_quantity_not_the_main_order_quantity():
    db = SessionLocal()
    result = parse_message(db, "เอาข้าวหมกไก่ทอด 2 กล่อง เพิ่มน่องไก่ทอด 1 กล่อง")
    db.close()

    assert result.next_state == "collecting_delivery_details"
    assert [(item.product_name, item.quantity) for item in result.items] == [
        ("ข้าวหมกไก่ทอด", 2),
        ("น่องไก่ทอด", 1),
    ]


def test_conditional_sold_out_substitution_is_not_parsed_as_extra_products():
    db = SessionLocal()
    result = parse_message(db, "เอาข้าวหมกไก่ทอด 1 ถ้าไก่ทอดหมดเอาไก่ต้มแทนได้")
    db.close()

    assert [(item.product_name, item.quantity) for item in result.items] == [("ข้าวหมกไก่ทอด", 1)]
    assert result.items[0].fallback_product_name == "ข้าวหมกไก่ต้ม"


def test_conditional_sold_out_substitution_uses_verified_fallback_when_primary_is_out():
    db = SessionLocal()
    db.query(Product).filter(Product.sku == "SET-FRIED").update({"stock_quantity": 0})
    db.commit()
    result = parse_message(db, "เอาข้าวหมกไก่ทอด 1 ถ้าไก่ทอดหมดเอาไก่ต้มแทนได้")
    db.close()

    assert result.next_state == "collecting_delivery_details"
    assert [(item.product_name, item.quantity) for item in result.items] == [("ข้าวหมกไก่ต้ม", 1)]
    assert result.items[0].substitution_from == "ข้าวหมกไก่ทอด"


@pytest.mark.parametrize(
    ("text", "expected_items"),
    [
        ("เอาข้าวหมกไก่ทอด 1 กับน่องไก่ทอด 2", [("ข้าวหมกไก่ทอด", 1), ("น่องไก่ทอด", 2)]),
        ("รับข้าวหมกไก่ต้ม 1 ห่อ เพิ่มปีก 2", [("ข้าวหมกไก่ต้ม", 1), ("ปีกไก่ต้ม", 2)]),
        ("เอาข้าวหมกไก่ทอด 2 กล่อง เพิ่มน่องไก่ทอด 1 กล่อง", [("ข้าวหมกไก่ทอด", 2), ("น่องไก่ทอด", 1)]),
    ],
)
def test_multi_item_order_examples_keep_each_item_quantity(text, expected_items):
    db = SessionLocal()
    result = parse_message(db, text)
    db.close()

    assert result.next_state == "collecting_delivery_details"
    assert [(item.product_name, item.quantity) for item in result.items] == expected_items


def test_known_product_availability_question_answers_from_stock():
    db = SessionLocal()
    available = parse_message(db, "ข้าวหมกไก่ทอดยังมีไหม")
    db.query(Product).filter(Product.sku == "SET-FRIED").update({"stock_quantity": 0})
    db.commit()
    unavailable = parse_message(db, "ข้าวหมกไก่ทอดยังมีไหม")
    db.close()

    assert available.intent == "ask_availability"
    assert available.answer_text == "ขณะนี้มีข้าวหมกไก่ทอดครับ"
    assert unavailable.intent == "ask_admin"
    assert unavailable.handoff_reason == "stock_unavailable_or_unset"


def test_basic_three_turn_conversation_can_be_simulated_without_creating_an_order():
    db = SessionLocal()
    greeting = parse_message(db, "สวัสดี")
    availability = parse_message(db, "มีข้าวหมกไก่ทอดไหม")
    order = parse_message(db, "เอาข้าวหมกไก่ทอด 1")
    db.close()

    assert (greeting.intent, greeting.next_state, greeting.answer_text) == (
        "greeting", "awaiting_order", "สวัสดีครับ รับอะไรดีครับ"
    )
    assert (availability.intent, availability.next_state, availability.answer_text) == (
        "ask_availability", "answer_if_verified", "ขณะนี้มีข้าวหมกไก่ทอดครับ"
    )
    assert [(item.product_name, item.quantity) for item in order.items] == [("ข้าวหมกไก่ทอด", 1)]


def test_persistent_conversation_state_resolves_an_unambiguous_reference():
    db = SessionLocal()
    channel = Channel(type=ChannelType.facebook_page, external_id="test-page")
    db.add(channel)
    db.flush()
    customer = Customer(channel_id=channel.id, external_user_id="test-customer")
    db.add(customer)
    db.flush()
    conversation = Conversation(channel_id=channel.id, customer_id=customer.id)
    db.add(conversation)
    db.commit()

    greeting, state = advance_conversation_state(db, conversation.id, "สวัสดี")
    availability, state = advance_conversation_state(db, conversation.id, "มีข้าวหมกไก่ทอดไหม")
    order, state = advance_conversation_state(db, conversation.id, "เอาข้าวหมกไก่ทอด 1")
    reference, state = advance_conversation_state(db, conversation.id, "เอาอันนั้น 2")
    db.commit()

    assert greeting.next_state == "awaiting_order"
    assert availability.answer_text == "ขณะนี้มีข้าวหมกไก่ทอดครับ"
    assert [(item.product_name, item.quantity) for item in order.items] == [("ข้าวหมกไก่ทอด", 1)]
    assert [(item.product_name, item.quantity) for item in reference.items] == [("ข้าวหมกไก่ทอด", 2)]
    assert state.state == "collecting_delivery_details"
    db.close()


def test_context_reference_checks_the_requested_quantity_against_stock():
    db = SessionLocal()
    channel = Channel(type=ChannelType.facebook_page, external_id="context-stock-page")
    db.add(channel)
    db.flush()
    customer = Customer(channel_id=channel.id, external_user_id="context-stock-customer")
    db.add(customer)
    db.flush()
    conversation = Conversation(channel_id=channel.id, customer_id=customer.id)
    db.add(conversation)
    db.query(Product).filter(Product.sku == "SET-FRIED").update({"stock_quantity": 1})
    db.commit()

    advance_conversation_state(db, conversation.id, "เอาข้าวหมกไก่ทอด 1")
    result, state = advance_conversation_state(db, conversation.id, "เอาอันนั้น 2")

    assert result.next_state == "waiting_for_admin"
    assert result.handoff_reason == "stock_unavailable_or_unset"
    assert state.last_items[0]["product_name"] == "ข้าวหมกไก่ทอด"
    db.close()


def test_context_reference_with_multiple_previous_items_is_sent_to_admin():
    db = SessionLocal()
    channel = Channel(type=ChannelType.facebook_page, external_id="context-ambiguous-page")
    db.add(channel)
    db.flush()
    customer = Customer(channel_id=channel.id, external_user_id="context-ambiguous-customer")
    db.add(customer)
    db.flush()
    conversation = Conversation(channel_id=channel.id, customer_id=customer.id)
    db.add(conversation)
    db.commit()

    advance_conversation_state(db, conversation.id, "เอาข้าวหมกไก่ทอด 1 กับน่องไก่ทอด 1")
    result, _ = advance_conversation_state(db, conversation.id, "เอาอันนั้นอีก 1")

    assert result.next_state == "waiting_for_admin"
    assert result.handoff_reason == "context_reference_requires_admin"
    db.close()


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("เอาข้าวหมกไก่ทอด 1 ไม่เอาผัก เอาแต่แตงกวา", "customization_requires_admin"),
        ("เอาข้าวหมกไก่ทอด 1 แต่แยกกันจ่ายนะคะ", "split_payment_requires_admin"),
        ("เอาข้าวหมกไก่ทอด 1 ส่งที่เดิมนะคะ", "delivery_context_requires_admin"),
        ("ออเดอร์ไม่ครบค่ะ", "complaint_requires_admin"),
        ("โอนไม่ได้ครับ", "payment_issue_requires_admin"),
        ("เอาสไปร์แทนค่ะ", "replacement_context_requires_admin"),
    ],
)
def test_operational_or_ambiguous_messages_are_never_silently_accepted(text, reason):
    db = SessionLocal()
    result = parse_message(db, text)
    db.close()

    assert result.next_state == "waiting_for_admin"
    assert result.handoff_reason == reason
    assert result.items == []


@pytest.mark.parametrize(
    ("text", "expected_name", "expected_quantity"),
    [
        ("เอาข้าวหมกไก่ทอด 2 กล่อง เพิ่มน่อง", "น่องไก่ทอด", 1),
        ("เอาข้าวหมกไก่ต้ม 1 ห่อ เพิ่มปีก 2", "ปีกไก่ต้ม", 2),
    ],
)
def test_abbreviated_chicken_part_reuses_the_ordered_preparation(text, expected_name, expected_quantity):
    db = SessionLocal()
    result = parse_message(db, text)
    db.close()

    assert result.next_state == "collecting_delivery_details"
    assert [(item.product_name, item.quantity) for item in result.items][1] == (expected_name, expected_quantity)


def test_abbreviated_chicken_part_is_not_inferred_from_mixed_chicken():
    db = SessionLocal()
    result = parse_message(db, "เอาข้าวหมกไก่ผสม 1 กล่อง เพิ่มน่อง")
    db.close()

    assert result.next_state == "waiting_for_admin"
    assert result.handoff_reason == "addition_requires_confirmation"


def test_any_matched_order_item_with_zero_stock_is_sent_to_admin():
    db = SessionLocal()
    db.query(Product).filter(Product.sku == "SET-FRIED").update({"stock_quantity": 0})
    db.commit()
    result = parse_message(db, "เอาข้าวหมกไก่ทอด 2 กล่อง")
    db.close()

    assert result.intent == "start_order"
    assert result.next_state == "waiting_for_admin"
    assert result.handoff_reason == "stock_unavailable_or_unset"
    assert result.items == []


def test_order_quantity_must_not_exceed_available_stock():
    db = SessionLocal()
    db.query(Product).filter(Product.sku == "SET-FRIED").update({"stock_quantity": 1})
    db.commit()
    result = parse_message(db, "เอาข้าวหมกไก่ทอด 2 กล่อง")
    db.close()

    assert result.next_state == "waiting_for_admin"
    assert result.handoff_reason == "stock_unavailable_or_unset"
    assert result.candidates[0]["requested_quantity"] == 2
    assert result.candidates[0]["available_quantity"] == 1


def test_unmatched_addition_is_not_ignored_when_main_item_is_in_stock():
    db = SessionLocal()
    db.query(Product).filter(Product.category == "ไก่").update({"stock_quantity": 0})
    db.commit()
    result = parse_message(db, "เอาข้าวหมกไก่ทอด 2 กล่อง เพิ่มไก่")
    db.close()

    assert result.intent == "start_order"
    assert result.next_state == "waiting_for_admin"
    assert result.handoff_reason == "stock_unavailable_or_unset"
    assert result.items == []


def test_test_api_logs_only_redacted_handoff_and_admin_resolution():
    response = client.post(
        "/api/parser-v2/test",
        json={"text": "เอาน้ำส้ม ส่งที่ 12/9 โทร 0812345678"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["handoff_reason"] == "unmatched_product"
    assert body["handoff_id"] is not None

    db = SessionLocal()
    handoff = db.get(AdminHandoffLog, body["handoff_id"])
    assert handoff is not None
    assert "0812345678" not in handoff.redacted_text
    assert "12/9" not in handoff.redacted_text
    db.close()

    resolved = client.post(
        f"/api/parser-v2/handoffs/{body['handoff_id']}/resolve",
        json={"resolution": "ไม่รับรายการนี้ โทร 0899999999"},
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["status"] == "resolved"
    assert "0899999999" not in resolved.json()["resolution"]


def test_parser_v2_does_not_create_a_live_draft_order():
    response = client.post("/api/parser-v2/test", json={"text": "เอาข้าวหมกไก่ทอด 1 ห่อ"})
    assert response.status_code == 200, response.text
    drafts = client.get("/api/draft-orders")
    assert drafts.status_code == 200, drafts.text
    assert drafts.json() == []


def test_restock_all_adds_ten_to_every_product_and_creates_audit_movements():
    response = client.post("/api/products/restock-all")
    assert response.status_code == 200, response.text
    assert response.json() == {"adjusted_count": 7, "change_per_product": 10}

    db = SessionLocal()
    tracked = db.query(Product).filter(Product.stock_mode == "tracked").all()
    unlimited = db.query(Product).filter(Product.stock_mode == "unlimited").all()
    assert {product.stock_quantity for product in tracked} == {20}
    assert len(unlimited) == 1
    assert unlimited[0].stock_quantity == 0
    movements = db.query(StockMovement).all()
    assert len(movements) == 7
    assert {movement.change for movement in movements} == {10}
    assert {movement.note for movement in movements} == {"เติมสต็อกทั้งหมด +10"}
    db.close()
