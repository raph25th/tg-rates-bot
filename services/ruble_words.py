from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


_ONES_MASCULINE = {
    1: "один",
    2: "два",
    3: "три",
    4: "четыре",
    5: "пять",
    6: "шесть",
    7: "семь",
    8: "восемь",
    9: "девять",
}
_ONES_FEMININE = {
    **_ONES_MASCULINE,
    1: "одна",
    2: "две",
}
_TEENS = {
    10: "десять",
    11: "одиннадцать",
    12: "двенадцать",
    13: "тринадцать",
    14: "четырнадцать",
    15: "пятнадцать",
    16: "шестнадцать",
    17: "семнадцать",
    18: "восемнадцать",
    19: "девятнадцать",
}
_TENS = {
    2: "двадцать",
    3: "тридцать",
    4: "сорок",
    5: "пятьдесят",
    6: "шестьдесят",
    7: "семьдесят",
    8: "восемьдесят",
    9: "девяносто",
}
_HUNDREDS = {
    1: "сто",
    2: "двести",
    3: "триста",
    4: "четыреста",
    5: "пятьсот",
    6: "шестьсот",
    7: "семьсот",
    8: "восемьсот",
    9: "девятьсот",
}


def _choose_form(number: int, forms: tuple[str, str, str]) -> str:
    last_two = number % 100
    if 11 <= last_two <= 14:
        return forms[2]
    last_digit = number % 10
    if last_digit == 1:
        return forms[0]
    if 2 <= last_digit <= 4:
        return forms[1]
    return forms[2]


def _three_digits_to_words(number: int, *, feminine: bool = False) -> list[str]:
    words: list[str] = []
    hundreds = number // 100
    remainder = number % 100
    if hundreds:
        words.append(_HUNDREDS[hundreds])
    if 10 <= remainder <= 19:
        words.append(_TEENS[remainder])
        return words
    tens = remainder // 10
    ones = remainder % 10
    if tens:
        words.append(_TENS[tens])
    if ones:
        words.append((_ONES_FEMININE if feminine else _ONES_MASCULINE)[ones])
    return words


def _integer_to_words(number: int) -> str:
    if number == 0:
        return "ноль"

    groups: list[tuple[int, int]] = []
    group_index = 0
    while number:
        groups.append((number % 1000, group_index))
        number //= 1000
        group_index += 1

    parts: list[str] = []
    for group, index in reversed(groups):
        if group == 0:
            continue
        feminine = index == 1
        parts.extend(_three_digits_to_words(group, feminine=feminine))
        if index == 1:
            parts.append(_choose_form(group, ("тысяча", "тысячи", "тысяч")))
        elif index == 2:
            parts.append(_choose_form(group, ("миллион", "миллиона", "миллионов")))
        elif index == 3:
            parts.append(_choose_form(group, ("миллиард", "миллиарда", "миллиардов")))
    return " ".join(parts)


def amount_to_russian_words(amount: Decimal) -> str:
    rounded = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    rubles = int(rounded)
    kopecks = int((rounded - Decimal(rubles)) * Decimal("100"))
    ruble_form = _choose_form(rubles, ("рубль", "рубля", "рублей"))
    kopeck_form = _choose_form(kopecks, ("копейка", "копейки", "копеек"))
    text = f"{_integer_to_words(rubles)} {ruble_form} {kopecks:02d} {kopeck_form}"
    return text[:1].upper() + text[1:]
