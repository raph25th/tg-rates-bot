from handlers.converter import (
    INVESTING_CALC_UNAVAILABLE_TEXT,
    get_capabilities_hint,
    get_new_calculation_hint,
)


def test_capabilities_hint_covers_supported_examples() -> None:
    hint = get_capabilities_hint()

    assert "💱 Что умеет бот" in hint
    assert "• 100 usd" in hint
    assert "• 10 000 aed +2%" in hint
    assert "• 1 000 000 rub в usd" in hint
    assert "• 10 000 usd в руб -1,5%" in hint
    assert "USD, EUR, CNY, GBP, AED, THB, KRW, JPY" in hint
    assert "56 548 468 рублей в USD" in hint


def test_new_calculation_hint_is_short() -> None:
    hint = get_new_calculation_hint()

    assert "💱 Новый расчёт" in hint
    assert "100 usd" in hint
    assert "10 000 usd +2%" in hint
    assert "1 000 000 rub в usd" in hint
    assert "❓ Что умеет бот" in hint


def test_investing_calculation_unavailable_message() -> None:
    assert "⚡ Расчёт по курсу Investing" in INVESTING_CALC_UNAVAILABLE_TEXT
    assert "Скоро здесь будет расчёт по live-курсу Investing." in INVESTING_CALC_UNAVAILABLE_TEXT
    assert "100 usd" in INVESTING_CALC_UNAVAILABLE_TEXT
