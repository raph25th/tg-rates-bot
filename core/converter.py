from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from core.models import CurrencyRate, RatesSnapshot
from core.money import format_number, format_plain_amount, format_rate
from services.conversion_parser import (
    RUB_CODE,
    SUPPORTED_CURRENCIES,
    ConversionRequest,
    is_supported_conversion_request,
    is_supported_currency,
    looks_like_convert_attempt,
    parse_conversion_request,
)

SUPPORTED_CALCULATOR_CURRENCIES = SUPPORTED_CURRENCIES
DEFAULT_CBR_SOURCE = "ЦБ РФ — официальный курс"
MARKET_RATE_NOTICE = "Рыночный курс является ориентиром и может отличаться от банков, обменников и торговых платформ."
AGENT_FEE_PERCENT = Decimal("0.1")


@dataclass(frozen=True)
class ConvertRequest:
    amount: Decimal
    from_code: str
    to_code: str = RUB_CODE
    percent: Decimal | None = None
    extra_payment_amount: Decimal | None = None
    direction: str = "currency_to_rub"
    is_agent_calculation: bool = False
    client_percent: Decimal | None = None
    main_rate_percent: Decimal | None = None
    agent_fee_percent: Decimal = AGENT_FEE_PERCENT
    extra_payment_usd: Decimal | None = None

    @property
    def code(self) -> str:
        return self.from_code

    @property
    def is_reverse(self) -> bool:
        return self.direction == "rub_to_currency"


@dataclass(frozen=True)
class ConversionResult:
    request: ConvertRequest
    result: Decimal
    rate: CurrencyRate
    adjusted_unit_rate: Decimal
    main_payment_rub: Decimal | None = None
    extra_payment_amount: Decimal | None = None
    extra_payment_rate: CurrencyRate | None = None
    adjusted_extra_payment_unit_rate: Decimal | None = None
    extra_payment_rub: Decimal | None = None
    final_result: Decimal | None = None
    source: str = DEFAULT_CBR_SOURCE

    @property
    def result_rub(self) -> Decimal:
        return self.result if self.request.to_code == RUB_CODE else self.request.amount


@dataclass(frozen=True)
class AgentCalculationResult:
    request: ConvertRequest
    rate: CurrencyRate
    adjusted_unit_rate: Decimal
    client_percent: Decimal
    main_rate_percent: Decimal
    agent_fee_percent: Decimal
    main_currency_payment_rub: Decimal
    extra_payment_usd: Decimal | None
    extra_payment_rate: CurrencyRate | None
    adjusted_extra_payment_unit_rate: Decimal | None
    extra_payment_rub: Decimal | None
    main_payment_rub: Decimal
    agent_fee_rub: Decimal
    final_result: Decimal
    source: str = DEFAULT_CBR_SOURCE


def parse_convert_request(text: str) -> ConvertRequest | None:
    parsed = parse_conversion_request(text)
    if parsed is None:
        return None
    return convert_parser_request(parsed)


def convert_parser_request(request: ConversionRequest) -> ConvertRequest:
    return ConvertRequest(
        amount=request.amount,
        from_code=request.from_currency,
        to_code=request.to_currency,
        percent=request.percent_adjustment,
        extra_payment_amount=request.extra_payment_amount,
        direction=request.direction,
        is_agent_calculation=request.is_agent_calculation,
        client_percent=request.client_percent,
        main_rate_percent=request.main_rate_percent,
        agent_fee_percent=request.agent_fee_percent,
        extra_payment_usd=request.extra_payment_usd,
    )


def is_supported_request(request: ConvertRequest) -> bool:
    return is_supported_conversion_request(
        ConversionRequest(
            amount=request.amount,
            from_currency=request.from_code,
            to_currency=request.to_code,
            percent_adjustment=request.percent,
            extra_payment_amount=request.extra_payment_amount,
            direction=request.direction,
            is_agent_calculation=request.is_agent_calculation,
            client_percent=request.client_percent,
            main_rate_percent=request.main_rate_percent,
            agent_fee_percent=request.agent_fee_percent,
            extra_payment_usd=request.extra_payment_usd,
        )
    )


def apply_percent(unit_rate: Decimal, percent: Decimal | None) -> Decimal:
    if percent is None:
        return unit_rate
    return unit_rate * (Decimal("1") + percent / Decimal("100"))


def convert_currency(
    request: ConvertRequest,
    snapshot: RatesSnapshot,
    source: str = DEFAULT_CBR_SOURCE,
) -> ConversionResult | None:
    if request.direction == "rub_to_currency":
        if request.extra_payment_amount is not None:
            return None
        rate = snapshot.rates.get(request.to_code)
        if rate is None:
            return None
        adjusted_rate = apply_percent(rate.unit_rate, request.percent)
        result_amount = request.amount / adjusted_rate
        return ConversionResult(
            request=request,
            result=result_amount,
            rate=rate,
            adjusted_unit_rate=adjusted_rate,
            final_result=result_amount,
            source=source,
        )

    rate = snapshot.rates.get(request.from_code)
    if rate is None:
        return None

    extra_payment_rate = snapshot.rates.get("USD") if request.extra_payment_amount is not None else None
    if request.extra_payment_amount is not None and extra_payment_rate is None:
        return None

    adjusted_rate = apply_percent(rate.unit_rate, request.percent)
    main_payment_rub = request.amount * adjusted_rate
    extra_payment_amount = request.extra_payment_amount
    adjusted_extra_payment_rate = (
        apply_percent(extra_payment_rate.unit_rate, request.percent)
        if extra_payment_rate is not None
        else None
    )
    extra_payment_rub = (
        extra_payment_amount * adjusted_extra_payment_rate
        if extra_payment_amount is not None and adjusted_extra_payment_rate is not None
        else None
    )
    final_result = main_payment_rub + (extra_payment_rub or Decimal("0"))
    return ConversionResult(
        request=request,
        result=final_result,
        rate=rate,
        adjusted_unit_rate=adjusted_rate,
        main_payment_rub=main_payment_rub,
        extra_payment_amount=extra_payment_amount,
        extra_payment_rate=extra_payment_rate,
        adjusted_extra_payment_unit_rate=adjusted_extra_payment_rate,
        extra_payment_rub=extra_payment_rub,
        final_result=final_result,
        source=source,
    )


def convert_agent_calculation(
    request: ConvertRequest,
    snapshot: RatesSnapshot,
    source: str = DEFAULT_CBR_SOURCE,
) -> AgentCalculationResult | None:
    if request.direction != "currency_to_rub" or request.percent is None:
        return None

    client_percent = request.percent
    agent_fee_percent = request.agent_fee_percent
    if client_percent <= agent_fee_percent:
        return None

    rate = snapshot.rates.get(request.from_code)
    if rate is None:
        return None

    extra_payment_usd = request.extra_payment_usd or request.extra_payment_amount
    extra_payment_rate = snapshot.rates.get("USD") if extra_payment_usd is not None else None
    if extra_payment_usd is not None and extra_payment_rate is None:
        return None

    main_rate_percent = client_percent - agent_fee_percent
    adjusted_rate = apply_percent(rate.unit_rate, main_rate_percent)
    main_currency_payment_rub = request.amount * adjusted_rate
    adjusted_extra_payment_rate = (
        apply_percent(extra_payment_rate.unit_rate, main_rate_percent)
        if extra_payment_rate is not None
        else None
    )
    extra_payment_rub = (
        extra_payment_usd * adjusted_extra_payment_rate
        if extra_payment_usd is not None and adjusted_extra_payment_rate is not None
        else None
    )
    main_payment_rub = main_currency_payment_rub + (extra_payment_rub or Decimal("0"))
    agent_fee_rub = main_payment_rub * agent_fee_percent / Decimal("100")
    final_result = main_payment_rub + agent_fee_rub

    return AgentCalculationResult(
        request=request,
        rate=rate,
        adjusted_unit_rate=adjusted_rate,
        client_percent=client_percent,
        main_rate_percent=main_rate_percent,
        agent_fee_percent=agent_fee_percent,
        main_currency_payment_rub=main_currency_payment_rub,
        extra_payment_usd=extra_payment_usd,
        extra_payment_rate=extra_payment_rate,
        adjusted_extra_payment_unit_rate=adjusted_extra_payment_rate,
        extra_payment_rub=extra_payment_rub,
        main_payment_rub=main_payment_rub,
        agent_fee_rub=agent_fee_rub,
        final_result=final_result,
        source=source,
    )


def format_percent(percent: Decimal) -> str:
    sign = "+" if percent >= 0 else ""
    text = format(percent.normalize(), "f").replace(".", ",")
    return f"{sign}{text}%"


def format_plain_percent(percent: Decimal) -> str:
    text = format(percent.normalize(), "f").replace(".", ",")
    return f"{text}%"


def get_agent_assignment_rate(result: AgentCalculationResult) -> Decimal:
    return result.main_payment_rub / result.request.amount


def format_agent_assignment_rate(result: AgentCalculationResult) -> str:
    return f"1 {result.rate.code} = {format_rate(get_agent_assignment_rate(result))} RUB"


def format_rub(value: Decimal) -> str:
    return f"{format_number(value, places=2, trim_zero_fraction=False)} RUB"


def format_currency_amount(value: Decimal, code: str) -> str:
    if code == RUB_CODE:
        return format_rub(value)
    return f"{format_number(value, places=2, trim_zero_fraction=False)} {code}"


def format_input_amount(request: ConvertRequest) -> str:
    if request.from_code == RUB_CODE:
        return f"{format_plain_amount(request.amount)} RUB"
    return f"{format_plain_amount(request.amount)} {request.from_code}"


def format_extra_payment_amount(result: ConversionResult) -> str:
    amount = result.extra_payment_amount or Decimal("0")
    return f"{format_plain_amount(amount)} USD"


def has_extra_payment(result: ConversionResult) -> bool:
    return (
        result.request.direction == "currency_to_rub"
        and result.extra_payment_amount is not None
        and result.extra_payment_rub is not None
        and result.main_payment_rub is not None
    )


def format_calculator_result(result: ConversionResult) -> str:
    return format_client_calculation_text(result)


def format_client_calculation_text(result: ConversionResult) -> str:
    request = result.request
    rate = result.rate
    title = "Расчёт валюты:" if request.direction == "rub_to_currency" else "Расчёт стоимости:"
    lines = [
        title,
        "",
        f"Сумма: {format_input_amount(request)}",
        f"Актуальный курс: 1 {rate.code} = {format_rate(rate.unit_rate)} RUB",
    ]

    if request.percent is not None:
        lines.append(f"Ставка: {format_percent(request.percent)}")
        if result.adjusted_unit_rate != rate.unit_rate:
            lines.append(f"Расчётный курс: 1 {rate.code} = {format_rate(result.adjusted_unit_rate)} RUB")

    if has_extra_payment(result):
        main_payment = result.main_payment_rub or Decimal("0")
        extra_payment = result.extra_payment_rub or Decimal("0")
        extra_payment_line = f"{format_extra_payment_amount(result)} = {format_rub(extra_payment)}"
        if result.rate.code != "USD" and result.adjusted_extra_payment_unit_rate is not None:
            extra_payment_line = (
                f"{format_extra_payment_amount(result)} × "
                f"{format_rate(result.adjusted_extra_payment_unit_rate)} RUB = {format_rub(extra_payment)}"
            )
        lines.extend(
            [
                "",
                "Основной платёж:",
                f"{format_input_amount(request)} = {format_rub(main_payment)}",
                "",
                "Доп. платёж:",
                extra_payment_line,
                "",
                "Итого:",
                f"{format_rub(main_payment)} + {format_rub(extra_payment)} = {format_rub(result.result)}",
            ]
        )
    else:
        lines.extend(
            [
                "",
                f"Итого: {format_currency_amount(result.result, request.to_code)}",
            ]
        )
    return "\n".join(lines)


def format_agent_calculation_result(result: AgentCalculationResult) -> str:
    request = result.request
    rate = result.rate
    lines = [
        f"Агентский расчёт на {rate.date.strftime('%d.%m.%Y')}",
        "",
        "Актуальный курс:",
        f"1 {rate.code} = {format_rate(rate.unit_rate)} RUB",
        "",
        "Сумма инвойса:",
        format_input_amount(request),
        "",
        "Ставка клиенту:",
    ]

    client_percent = format_plain_percent(result.client_percent)
    main_percent = format_plain_percent(result.main_rate_percent)
    agent_percent = format_plain_percent(result.agent_fee_percent)
    if result.extra_payment_usd is None:
        lines.append(f"{client_percent} = {main_percent} + {agent_percent}")
    else:
        extra_text = f"{format_plain_amount(result.extra_payment_usd)} USD"
        lines.append(f"{client_percent} + {extra_text} = {main_percent} + {agent_percent} + {extra_text}")

    lines.extend(
        [
            "",
            "Расчётный курс:",
            f"{format_rate(rate.unit_rate)} + {main_percent} = {format_rate(result.adjusted_unit_rate)} RUB",
        ]
    )

    if (
        result.extra_payment_usd is not None
        and rate.code != "USD"
        and result.adjusted_extra_payment_unit_rate is not None
        and result.extra_payment_rate is not None
    ):
        lines.extend(
            [
                "",
                "Курс USD для доп. платежа:",
                f"{format_rate(result.extra_payment_rate.unit_rate)} + {main_percent} = {format_rate(result.adjusted_extra_payment_unit_rate)} RUB",
            ]
        )

    lines.extend(
        [
            "",
            "Основной платёж:",
            f"{format_input_amount(request)} × {format_rate(result.adjusted_unit_rate)} = {format_rub(result.main_currency_payment_rub)}",
        ]
    )
    if result.extra_payment_usd is not None and result.extra_payment_rub is not None:
        usd_rate = result.adjusted_extra_payment_unit_rate or result.adjusted_unit_rate
        lines.extend(
            [
                "",
                "Фиксированное ПП:",
                f"{format_plain_amount(result.extra_payment_usd)} USD × {format_rate(usd_rate)} = {format_rub(result.extra_payment_rub)}",
                "",
                "Итого основной платёж:",
                format_rub(result.main_payment_rub),
                "",
                "Курс в поручении:",
                format_agent_assignment_rate(result),
            ]
        )

    lines.extend(
        [
            "",
            "Агентское вознаграждение:",
            f"{format_rub(result.main_payment_rub)} × {agent_percent} = {format_rub(result.agent_fee_rub)}",
            "",
            "Итого:",
            f"Основной платёж: {format_rub(result.main_payment_rub)}",
            f"Агентское вознаграждение: {format_rub(result.agent_fee_rub)}",
            "",
            "Итоговая сумма:",
            format_rub(result.final_result),
        ]
    )
    return "\n".join(lines)


def format_conversion(amount: Decimal, code: str, result_rub: Decimal) -> str:
    return f"{format_plain_amount(amount)} {code.upper()} = {format_number(result_rub)} RUB"
