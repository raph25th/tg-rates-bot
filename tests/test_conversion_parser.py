from decimal import Decimal

from services.conversion_parser import parse_conversion_request


def assert_request(
    text: str,
    amount: str,
    from_currency: str,
    to_currency: str,
    percent: str | None,
    direction: str,
) -> None:
    request = parse_conversion_request(text)

    assert request is not None
    assert request.amount == Decimal(amount)
    assert request.from_currency == from_currency
    assert request.to_currency == to_currency
    assert request.percent_adjustment == (Decimal(percent) if percent is not None else None)
    assert request.direction == direction


def test_parse_currency_to_rub_variants() -> None:
    assert_request("100 usd", "100", "USD", "RUB", None, "currency_to_rub")
    assert_request("100 usd rub", "100", "USD", "RUB", None, "currency_to_rub")
    assert_request("100 usd в руб", "100", "USD", "RUB", None, "currency_to_rub")
    assert_request("10 000 usd +2%", "10000", "USD", "RUB", "2", "currency_to_rub")
    assert_request("10 000 usd в руб +2%", "10000", "USD", "RUB", "2", "currency_to_rub")
    assert_request("10000 aed в руб +3%", "10000", "AED", "RUB", "3", "currency_to_rub")
    assert_request("10 000 usd по цб +2%", "10000", "USD", "RUB", "2", "currency_to_rub")


def test_parse_rub_to_currency_variants() -> None:
    assert_request("56548468 rub usd", "56548468", "RUB", "USD", None, "rub_to_currency")
    assert_request("56548468 rub в USD", "56548468", "RUB", "USD", None, "rub_to_currency")
    assert_request("56 548 468 рублей в usd", "56548468", "RUB", "USD", None, "rub_to_currency")
    assert_request("1 000 000 ₽ в eur", "1000000", "RUB", "EUR", None, "rub_to_currency")
    assert_request("56548468 rub в usd -1.5%", "56548468", "RUB", "USD", "-1.5", "rub_to_currency")


def test_parse_percent_words_and_comma() -> None:
    assert_request("100 usd плюс 2%", "100", "USD", "RUB", "2", "currency_to_rub")
    assert_request("100 usd минус 1,5%", "100", "USD", "RUB", "-1.5", "currency_to_rub")


def test_parse_new_currencies() -> None:
    assert_request("1000000 krw", "1000000", "KRW", "RUB", None, "currency_to_rub")
    assert_request("500000 jpy", "500000", "JPY", "RUB", None, "currency_to_rub")


def test_unknown_currency_is_parsed_for_handler_error() -> None:
    assert_request("100 xyz", "100", "XYZ", "RUB", None, "currency_to_rub")


def test_invalid_format() -> None:
    assert parse_conversion_request("hello") is None
    assert parse_conversion_request("100") is None
    assert parse_conversion_request("-100 usd") is None
    assert parse_conversion_request("100 usd eur") is None
