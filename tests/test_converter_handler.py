from handlers.converter import (
    INVESTING_CALC_UNAVAILABLE_TEXT,
    calculator_result_keyboard,
    get_capabilities_hint,
    get_new_calculation_hint,
)


def test_capabilities_hint_covers_supported_examples() -> None:
    hint = get_capabilities_hint()

    assert "❓ Что умеет бот" in hint
    assert "• считать по официальному курсу ЦБ РФ" in hint
    assert "• считать по рыночному курсу, если источник подключён" in hint
    assert "• применять процентную корректировку к курсу" in hint
    assert "• считать валюту в рубли и рубли в валюту" in hint
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
    assert "Больше возможностей — в разделе:" in hint
    assert "❓ Что умеет бот" in hint


def test_calculator_result_keyboard_has_only_new_calc_and_main_menu() -> None:
    keyboard = calculator_result_keyboard()
    buttons = [button for row in keyboard.inline_keyboard for button in row]

    assert [(button.text, button.callback_data) for button in buttons] == [
        ("🔁 Новый расчёт", "calc:new"),
        ("🏠 Главное меню", "main_menu"),
    ]


def test_investing_calculation_unavailable_message() -> None:
    assert "💱 Расчёт по рынку" in INVESTING_CALC_UNAVAILABLE_TEXT
    assert "Рыночные курсы временно недоступны." in INVESTING_CALC_UNAVAILABLE_TEXT
    assert "100 usd" in INVESTING_CALC_UNAVAILABLE_TEXT
