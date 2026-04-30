from datetime import date

from services.cbr_date_parser import parse_cbr_date


def test_parse_dot_date() -> None:
    assert parse_cbr_date("23.04.2026") == date(2026, 4, 23)


def test_parse_dash_date() -> None:
    assert parse_cbr_date("23-04-2026") == date(2026, 4, 23)


def test_parse_slash_date() -> None:
    assert parse_cbr_date("23/04/2026") == date(2026, 4, 23)


def test_parse_full_russian_month_without_year() -> None:
    assert parse_cbr_date("23 апреля", today=date(2026, 5, 1)) == date(2026, 4, 23)


def test_parse_short_russian_month_without_year() -> None:
    assert parse_cbr_date("23 апр", today=date(2026, 5, 1)) == date(2026, 4, 23)


def test_parse_short_english_month_without_year() -> None:
    assert parse_cbr_date("23 apr", today=date(2026, 5, 1)) == date(2026, 4, 23)


def test_parse_invalid_date() -> None:
    assert parse_cbr_date("31.02.2026") is None
    assert parse_cbr_date("завтра") is None
