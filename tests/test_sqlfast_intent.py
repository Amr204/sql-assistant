"""Intent router for SQL fast path vs Vanna agent."""

from __future__ import annotations

from vai_agent.sqlfast.intent_router import ChatPath, needs_enhanced_context, route_intent


def test_route_intent_arabic_count_customers() -> None:
    q = "كم به معنا عملاء من اسبانيا"
    assert route_intent(q) is ChatPath.SQL_FAST


def test_route_intent_arabic_bottom_sales() -> None:
    q = "اشتي تبصر لي أضعف 5 عملاء بالمبيعات"
    assert route_intent(q) is ChatPath.SQL_FAST


def test_route_intent_english_count() -> None:
    assert route_intent("How many customers are in France?") is ChatPath.SQL_FAST


def test_route_intent_vanna_for_smalltalk() -> None:
    assert route_intent("hello") is ChatPath.VANNA_AGENT


def test_needs_enhanced_context_arabic_join_hint() -> None:
    assert needs_enhanced_context("اعرض العملاء مع طلباتهم") is True


def test_needs_enhanced_context_english_distribution() -> None:
    assert needs_enhanced_context("Show revenue breakdown per region") is True


def test_needs_enhanced_context_simple_question_false() -> None:
    assert needs_enhanced_context("How many rows in Orders?") is False
