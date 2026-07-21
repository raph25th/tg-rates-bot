from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP

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
RATE_QUANT = Decimal("0.0001")


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
    invoice_base_rub: Decimal | None
    cross_rate: Decimal | None
    main_payment_rub: Decimal
    agent_fee_rub: Decimal
    final_result: Decimal
    source: str = DEFAULT_CBR_SOURCE


@dataclass(frozen=True)
class MaxInvoiceRequest:
    limit_rub: Decimal
    invoice_code: str
    percent: Decimal
    extra_payment_amount: Decimal | None = None
    extra_payment_code: str | None = None
    agent_fee_percent: Decimal = AGENT_FEE_PERCENT


@dataclass(frozen=True)
class MaxInvoiceResult:
    request: MaxInvoiceRequest
    rate: CurrencyRate
    adjusted_unit_rate: Decimal
    client_percent: Decimal
    main_rate_percent: Decimal
    agent_fee_percent: Decimal
    max_invoice_amount: Decimal
    main_payment_rub: Decimal
    agent_fee_rub: Decimal
    final_result: Decimal
    remainder_rub: Decimal
    invoice_base_rub: Decimal | None = None
    extra_payment_rate: CurrencyRate | None = None
    extra_payment_rub: Decimal | None = None
    cross_rate: Decimal | None = None
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


def round_rate_for_calculation(unit_rate: Decimal) -> Decimal:
    return unit_rate.quantize(RATE_QUANT, rounding=ROUND_HALF_UP)


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

    main_rate_percent = client_percent - agent_fee_percent
    adjusted_rate = round_rate_for_calculation(apply_percent(rate.unit_rate, main_rate_percent))

    invoice_base_rub = None
    cross_rate = None
    extra_payment_rub = None
    if extra_payment_usd is None:
        main_currency_payment_rub = request.amount * adjusted_rate
        main_payment_rub = main_currency_payment_rub
        adjusted_extra_payment_rate = None
    else:
        invoice_base_rub = request.amount * rate.unit_rate
        adjusted_extra_payment_rate = rate.unit_rate
        extra_payment_rub = extra_payment_usd * adjusted_extra_payment_rate
        cross_rate = (invoice_base_rub + extra_payment_rub) / request.amount
        calculation_rate = apply_percent(cross_rate, main_rate_percent)
        adjusted_rate = round_rate_for_calculation(calculation_rate)
        main_currency_payment_rub = request.amount * adjusted_rate
        main_payment_rub = main_currency_payment_rub

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
        extra_payment_rate=rate if extra_payment_usd is not None else None,
        adjusted_extra_payment_unit_rate=adjusted_extra_payment_rate,
        extra_payment_rub=extra_payment_rub,
        invoice_base_rub=invoice_base_rub,
        cross_rate=cross_rate,
        main_payment_rub=main_payment_rub,
        agent_fee_rub=agent_fee_rub,
        final_result=final_result,
        source=source,
    )


def _agent_total_from_main_payment(main_payment_rub: Decimal, agent_fee_percent: Decimal) -> tuple[Decimal, Decimal]:
    agent_fee_rub = main_payment_rub * agent_fee_percent / Decimal("100")
    return agent_fee_rub, main_payment_rub + agent_fee_rub


def _max_invoice_main_payment(
    amount: Decimal,
    invoice_rate: CurrencyRate,
    pp_rate: CurrencyRate | None,
    extra_payment_amount: Decimal | None,
    main_rate_percent: Decimal,
) -> tuple[Decimal, Decimal | None, Decimal | None, Decimal]:
    if extra_payment_amount is None or pp_rate is None:
        adjusted_rate = round_rate_for_calculation(apply_percent(invoice_rate.unit_rate, main_rate_percent))
        return amount * adjusted_rate, None, None, adjusted_rate

    invoice_base_rub = amount * invoice_rate.unit_rate
    extra_payment_rub = extra_payment_amount * pp_rate.unit_rate
    cross_rate = (invoice_base_rub + extra_payment_rub) / amount
    adjusted_rate = round_rate_for_calculation(apply_percent(cross_rate, main_rate_percent))
    return amount * adjusted_rate, invoice_base_rub, cross_rate, adjusted_rate


def calculate_max_invoice(
    request: MaxInvoiceRequest,
    snapshot: RatesSnapshot,
    source: str = DEFAULT_CBR_SOURCE,
) -> MaxInvoiceResult | None:
    if request.limit_rub <= 0 or request.percent <= request.agent_fee_percent:
        return None

    invoice_rate = snapshot.rates.get(request.invoice_code)
    if invoice_rate is None:
        return None

    extra_payment_amount = request.extra_payment_amount
    extra_payment_code = request.extra_payment_code or request.invoice_code
    extra_payment_rate = None
    extra_payment_rub = None
    if extra_payment_amount is not None:
        extra_payment_rate = snapshot.rates.get(extra_payment_code)
        if extra_payment_rate is None:
            return None
        extra_payment_rub = extra_payment_amount * extra_payment_rate.unit_rate

    main_rate_percent = request.percent - request.agent_fee_percent
    no_pp_rate = round_rate_for_calculation(apply_percent(invoice_rate.unit_rate, main_rate_percent))
    if no_pp_rate <= 0:
        return None
    agent_factor = Decimal("1") + request.agent_fee_percent / Decimal("100")
    no_pp_unit_total = no_pp_rate * agent_factor
    high_cents = int((request.limit_rub / no_pp_unit_total * Decimal("100")).to_integral_value(rounding=ROUND_FLOOR))
    if high_cents <= 0:
        return None

    if extra_payment_amount is None or extra_payment_rate is None:
        best_cents = high_cents
    else:
        working_factor = Decimal("1") + main_rate_percent / Decimal("100")
        base_rate_exact = invoice_rate.unit_rate * working_factor
        fixed_payment_exact = extra_payment_rub * working_factor
        available_before_fee = request.limit_rub / agent_factor - fixed_payment_exact
        minimum_effective_rate = base_rate_exact - RATE_QUANT / Decimal("2")
        if available_before_fee <= 0 or minimum_effective_rate <= 0:
            return None

        # Rounding makes the total locally non-monotonic. This bound follows from
        # rounded_rate >= exact_rate - 0.00005 and cannot exclude a valid amount.
        best_cents = int(
            (available_before_fee / minimum_effective_rate * Decimal("100")).to_integral_value(
                rounding=ROUND_FLOOR
            )
        )
        best_cents = min(best_cents, high_cents)

        while best_cents > 0:
            amount = Decimal(best_cents) / Decimal("100")
            main_payment_rub, _, _, adjusted_rate = _max_invoice_main_payment(
                amount,
                invoice_rate,
                extra_payment_rate,
                extra_payment_amount,
                main_rate_percent,
            )
            _, final_result = _agent_total_from_main_payment(main_payment_rub, request.agent_fee_percent)
            if final_result <= request.limit_rub:
                break

            affordable_cents = int(
                (request.limit_rub / (adjusted_rate * agent_factor) * Decimal("100")).to_integral_value(
                    rounding=ROUND_FLOOR
                )
            )
            best_cents = min(best_cents - 1, affordable_cents)

    if best_cents <= 0:
        return None

    max_invoice_amount = Decimal(best_cents) / Decimal("100")
    main_payment_rub, invoice_base_rub, cross_rate, adjusted_rate = _max_invoice_main_payment(
        max_invoice_amount,
        invoice_rate,
        extra_payment_rate,
        extra_payment_amount,
        main_rate_percent,
    )
    agent_fee_rub, final_result = _agent_total_from_main_payment(main_payment_rub, request.agent_fee_percent)
    remainder_rub = request.limit_rub - final_result

    return MaxInvoiceResult(
        request=request,
        rate=invoice_rate,
        adjusted_unit_rate=adjusted_rate,
        client_percent=request.percent,
        main_rate_percent=main_rate_percent,
        agent_fee_percent=request.agent_fee_percent,
        max_invoice_amount=max_invoice_amount,
        main_payment_rub=main_payment_rub,
        agent_fee_rub=agent_fee_rub,
        final_result=final_result,
        remainder_rub=remainder_rub,
        invoice_base_rub=invoice_base_rub,
        extra_payment_rate=extra_payment_rate,
        extra_payment_rub=extra_payment_rub,
        cross_rate=cross_rate,
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


def format_max_invoice_result(result: MaxInvoiceResult) -> str:
    request = result.request
    rate = result.rate
    client_percent = format_plain_percent(result.client_percent)
    main_percent = format_plain_percent(result.main_rate_percent)
    agent_percent = format_plain_percent(result.agent_fee_percent)
    invoice_amount_text = f"{format_number(result.max_invoice_amount, places=2, trim_zero_fraction=False)} {request.invoice_code}"

    lines = [
        f"Максимальная сумма инвойса на {rate.date.strftime('%d.%m.%Y')}",
        "",
        "Лимит клиента:",
        format_rub(request.limit_rub),
        "",
        "Актуальные курсы:",
        f"1 {rate.code} = {format_rate(rate.unit_rate)} RUB",
    ]

    extra_rate = result.extra_payment_rate
    if extra_rate is not None and extra_rate.code != rate.code:
        lines.append(f"1 {extra_rate.code} = {format_rate(extra_rate.unit_rate)} RUB")

    lines.extend(
        [
            "",
            "Ставка клиенту:",
        ]
    )

    if request.extra_payment_amount is None:
        lines.append(f"{client_percent} = {main_percent} + {agent_percent}")
    else:
        extra_code = extra_rate.code if extra_rate is not None else (request.extra_payment_code or request.invoice_code)
        extra_text = f"{format_plain_amount(request.extra_payment_amount)} {extra_code}"
        lines.append(f"{client_percent} + {extra_text} = {main_percent} + {agent_percent} + {extra_text}")

    lines.extend(
        [
            "",
        ]
    )

    if request.extra_payment_amount is None:
        lines.extend(
            [
                "Расчётный курс:",
                f"{format_rate(rate.unit_rate)} + {main_percent} = {format_rate(result.adjusted_unit_rate)} RUB",
            ]
        )
    elif (
        extra_rate is not None
        and result.extra_payment_rub is not None
        and result.invoice_base_rub is not None
        and result.cross_rate is not None
    ):
        extra_text = f"{format_plain_amount(request.extra_payment_amount)} {extra_rate.code}"
        lines.extend(
            [
                "Курс для расчёта ПП:",
                f"1 {extra_rate.code} = {format_rate(extra_rate.unit_rate)} RUB",
                "",
                f"Кросс-курс с учётом {extra_text}:",
                f"{invoice_amount_text} × {format_rate(rate.unit_rate)} = {format_rub(result.invoice_base_rub)}",
                f"{extra_text} × {format_rate(extra_rate.unit_rate)} = {format_rub(result.extra_payment_rub)}",
                f"({format_rub(result.invoice_base_rub)} + {format_rub(result.extra_payment_rub)}) / {invoice_amount_text} = {format_rate(result.cross_rate)} RUB",
                "",
                "Расчётный курс:",
                f"{format_rate(result.cross_rate)} + {main_percent} = {format_rate(result.adjusted_unit_rate)} RUB",
            ]
        )

    lines.extend(
        [
            "",
            "Максимальная сумма инвойса:",
            invoice_amount_text,
            "",
            "Основной платёж:",
            f"{invoice_amount_text} × {format_rate(result.adjusted_unit_rate)} = {format_rub(result.main_payment_rub)}",
            "",
            "Агентское вознаграждение:",
            f"{format_rub(result.main_payment_rub)} × {agent_percent} = {format_rub(result.agent_fee_rub)}",
            "",
            "Итоговая сумма:",
            format_rub(result.final_result),
            "",
            "Остаток от лимита:",
            format_rub(result.remainder_rub),
        ]
    )
    return "\n".join(lines)


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


def format_custom_calculation_result(result: ConversionResult) -> str:
    request = result.request
    rate = result.rate
    return "\n".join(
        [
            f"Расчёт по своему курсу на {rate.date.strftime('%d.%m.%Y')}",
            "",
            "Собственный курс:",
            f"1 {rate.code} = {format_rate(rate.unit_rate)} RUB",
            "",
            "Сумма инвойса:",
            format_input_amount(request),
            "",
            "Сумма по курсу:",
            f"{format_input_amount(request)} × {format_rate(result.adjusted_unit_rate)} = {format_rub(result.result)}",
        ]
    )


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
        extra_text = f"{format_plain_amount(result.extra_payment_usd)} {rate.code}"
        lines.append(f"{client_percent} + {extra_text} = {main_percent} + {agent_percent} + {extra_text}")

    lines.extend(
        [
            "",
        ]
    )

    if result.extra_payment_usd is None:
        lines.extend(
            [
                "Расчётный курс:",
                f"{format_rate(rate.unit_rate)} + {main_percent} = {format_rate(result.adjusted_unit_rate)} RUB",
            ]
        )
    elif (
        result.adjusted_extra_payment_unit_rate is not None
        and result.extra_payment_rub is not None
        and result.invoice_base_rub is not None
        and result.cross_rate is not None
    ):
        fixed_pp_text = f"{format_plain_amount(result.extra_payment_usd)} {rate.code}"
        lines.extend(
            [
                "Курс для расчёта ПП:",
                f"1 {rate.code} = {format_rate(result.adjusted_extra_payment_unit_rate)} RUB",
                "",
                f"Кросс-курс с учётом {fixed_pp_text}:",
                f"{format_input_amount(request)} × {format_rate(rate.unit_rate)} = {format_rub(result.invoice_base_rub)}",
                f"{fixed_pp_text} × {format_rate(result.adjusted_extra_payment_unit_rate)} = {format_rub(result.extra_payment_rub)}",
                f"({format_rub(result.invoice_base_rub)} + {format_rub(result.extra_payment_rub)}) / {format_input_amount(request)} = {format_rate(result.cross_rate)} RUB",
                "",
                "Расчётный курс:",
                f"{format_rate(result.cross_rate)} + {main_percent} = {format_rate(result.adjusted_unit_rate)} RUB",
            ]
        )

    lines.extend(
        [
            "",
            "Основной платёж:",
            f"{format_input_amount(request)} × {format_rate(result.adjusted_unit_rate)} = {format_rub(result.main_currency_payment_rub)}",
        ]
    )
    if result.extra_payment_usd is not None:
        lines.extend(
            [
                "",
                "Итого основной платёж:",
                format_rub(result.main_payment_rub),
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


def format_custom_agent_calculation_result(result: AgentCalculationResult) -> str:
    text = format_agent_calculation_result(result)
    return (
        text.replace("Агентский расчёт на ", "Агентский расчёт по своему курсу на ", 1)
        .replace("Актуальный курс:", "Собственный курс:", 1)
    )


def format_conversion(amount: Decimal, code: str, result_rub: Decimal) -> str:
    return f"{format_plain_amount(amount)} {code.upper()} = {format_number(result_rub)} RUB"
