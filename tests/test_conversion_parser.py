from decimal import Decimal

from services.conversion_parser import normalize_currency_token, parse_conversion_request


def assert_request(
    text: str,
    amount: str,
    from_currency: str,
    to_currency: str,
    percent: str | None,
    direction: str,
    extra_payment: str | None = None,
) -> None:
    request = parse_conversion_request(text)

    assert request is not None
    assert request.amount == Decimal(amount)
    assert request.from_currency == from_currency
    assert request.to_currency == to_currency
    assert request.percent_adjustment == (Decimal(percent) if percent is not None else None)
    assert request.extra_payment_amount == (Decimal(extra_payment) if extra_payment is not None else None)
    assert request.direction == direction


def test_parse_currency_to_rub_variants() -> None:
    assert_request("100 usd", "100", "USD", "RUB", None, "currency_to_rub")
    assert_request("100 usd rub", "100", "USD", "RUB", None, "currency_to_rub")
    assert_request("100 usd в руб", "100", "USD", "RUB", None, "currency_to_rub")
    assert_request("10 000 usd +2%", "10000", "USD", "RUB", "2", "currency_to_rub")
    assert_request("10,000 usd", "10000", "USD", "RUB", None, "currency_to_rub")
    assert_request("10.000 usd", "10000", "USD", "RUB", None, "currency_to_rub")
    assert_request("10 000 usd в руб +2%", "10000", "USD", "RUB", "2", "currency_to_rub")
    assert_request("10000 aed в руб +3%", "10000", "AED", "RUB", "3", "currency_to_rub")
    assert_request("10 000 usd по цб +2%", "10000", "USD", "RUB", "2", "currency_to_rub")
    assert_request("10 000 USD", "10000", "USD", "RUB", None, "currency_to_rub")


def test_parse_rub_to_currency_variants() -> None:
    assert_request("56548468 rub usd", "56548468", "RUB", "USD", None, "rub_to_currency")
    assert_request("56548468 rub в USD", "56548468", "RUB", "USD", None, "rub_to_currency")
    assert_request("1 000 000 rub в usd", "1000000", "RUB", "USD", None, "rub_to_currency")
    assert_request("56 548 468 рублей в usd", "56548468", "RUB", "USD", None, "rub_to_currency")
    assert_request("1 000 000 ₽ в eur", "1000000", "RUB", "EUR", None, "rub_to_currency")
    assert_request("56548468 rub в usd -1.5%", "56548468", "RUB", "USD", "-1.5", "rub_to_currency")


def test_parse_percent_words_and_comma() -> None:
    assert_request("100 usd плюс 2%", "100", "USD", "RUB", "2", "currency_to_rub")
    assert_request("100 usd минус 1,5%", "100", "USD", "RUB", "-1.5", "currency_to_rub")


def test_parse_percent_spacing_variants() -> None:
    cases = [
        ("100 usd +2%", "2"),
        ("100 usd + 2%", "2"),
        ("100 usd + 2 %", "2"),
        ("100 usd 2%", "2"),
        ("100 usd 2 %", "2"),
        ("100 usd -1.5%", "-1.5"),
        ("100 usd - 1.5%", "-1.5"),
        ("100 usd - 1,5%", "-1.5"),
        ("100 usd плюс 2%", "2"),
        ("100 usd минус 1,5%", "-1.5"),
        ("100 usd плюс 2 %", "2"),
    ]

    for text, percent in cases:
        assert_request(text, "100", "USD", "RUB", percent, "currency_to_rub")


def test_parse_extra_payment_variants() -> None:
    cases = [
        ("10000 usd +2% +100ПП", "2", "100"),
        ("10000 usd +2% +100 ПП", "2", "100"),
        ("10000 usd +2% +100$", "2", "100"),
        ("10000 usd +2% +100", "2", "100"),
        ("10000 usd +100ПП", None, "100"),
        ("10000 usd +100$", None, "100"),
    ]

    for text, percent, extra_payment in cases:
        assert_request(text, "10000", "USD", "RUB", percent, "currency_to_rub", extra_payment)


def test_parse_extra_payment_for_rub_to_currency_keeps_direction() -> None:
    assert_request("1 000 000 rub в usd +100ПП", "1000000", "RUB", "USD", None, "rub_to_currency", "100")


def test_parse_decimal_amounts() -> None:
    assert_request("10,5 usd", "10.5", "USD", "RUB", None, "currency_to_rub")
    assert_request("10.5 usd", "10.5", "USD", "RUB", None, "currency_to_rub")


def test_parse_currency_aliases() -> None:
    assert_request("10 000 юсд", "10000", "USD", "RUB", None, "currency_to_rub")
    assert_request("10 000 долларов", "10000", "USD", "RUB", None, "currency_to_rub")
    assert_request("10 000 баксов +2%", "10000", "USD", "RUB", "2", "currency_to_rub")
    assert_request("10 000 долларов в руб", "10000", "USD", "RUB", None, "currency_to_rub")
    assert_request("1 000 000 рублей в доллары", "1000000", "RUB", "USD", None, "rub_to_currency")
    assert_request("500 000 руб в евро", "500000", "RUB", "EUR", None, "rub_to_currency")
    assert_request("5 000 000 рублей в юани", "5000000", "RUB", "CNY", None, "rub_to_currency")


def test_normalize_currency_token_aliases() -> None:
    assert normalize_currency_token("юсд") == "USD"
    assert normalize_currency_token("долларов") == "USD"
    assert normalize_currency_token("евро") == "EUR"
    assert normalize_currency_token("рублей") == "RUB"
    assert normalize_currency_token("дирхам оаэ") == "AED"
    assert normalize_currency_token("фунт стерлингов") == "GBP"
    assert normalize_currency_token("корейская вона") == "KRW"


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
