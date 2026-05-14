from decimal import Decimal

from services.ruble_words import amount_to_russian_words


def test_amount_to_russian_words_examples() -> None:
    assert amount_to_russian_words(Decimal("775680.00")) == (
        "Семьсот семьдесят пять тысяч шестьсот восемьдесят рублей 00 копеек"
    )
    assert amount_to_russian_words(Decimal("775.68")) == "Семьсот семьдесят пять рублей 68 копеек"
    assert amount_to_russian_words(Decimal("776455.68")) == (
        "Семьсот семьдесят шесть тысяч четыреста пятьдесят пять рублей 68 копеек"
    )
    assert amount_to_russian_words(Decimal("1.01")) == "Один рубль 01 копейка"
    assert amount_to_russian_words(Decimal("2.02")) == "Два рубля 02 копейки"
    assert amount_to_russian_words(Decimal("5.05")) == "Пять рублей 05 копеек"
    assert amount_to_russian_words(Decimal("21.21")) == "Двадцать один рубль 21 копейка"
