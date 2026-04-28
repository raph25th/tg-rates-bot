from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Mapping
from xml.etree import ElementTree

from core.models import CurrencyRate, RatesSnapshot


class CBRServiceError(RuntimeError):
    pass


class CBRParseError(CBRServiceError):
    pass


def _node_text(node: ElementTree.Element, name: str) -> str:
    child = node.find(name)
    if child is None or child.text is None:
        raise CBRParseError(f"CBR XML is missing {name}")
    return child.text.strip()


def _parse_decimal(value: str) -> Decimal:
    return Decimal(value.replace(",", "."))


def parse_cbr_xml(payload: bytes | str) -> RatesSnapshot:
    try:
        root = ElementTree.fromstring(payload)
    except ElementTree.ParseError as exc:
        raise CBRParseError("CBR XML is not valid") from exc

    date_text = root.attrib.get("Date")
    if not date_text:
        raise CBRParseError("CBR XML is missing ValCurs Date")

    try:
        rate_date = datetime.strptime(date_text, "%d.%m.%Y").date()
    except ValueError as exc:
        raise CBRParseError(f"Unexpected CBR date format: {date_text}") from exc

    rates: dict[str, CurrencyRate] = {}
    for item in root.findall("Valute"):
        code = _node_text(item, "CharCode").upper()
        name = _node_text(item, "Name")
        nominal = int(_node_text(item, "Nominal"))
        value = _parse_decimal(_node_text(item, "Value"))
        if nominal <= 0:
            raise CBRParseError(f"Nominal for {code} must be positive")

        rates[code] = CurrencyRate(
            code=code,
            name=name,
            nominal=nominal,
            value=value,
            unit_rate=value / Decimal(nominal),
            date=rate_date,
        )

    if not rates:
        raise CBRParseError("CBR XML does not contain currencies")

    return RatesSnapshot(date=rate_date, rates=rates)


def calculate_deltas(
    current_rates: Mapping[str, CurrencyRate],
    previous_rates: Mapping[str, CurrencyRate],
) -> dict[str, Decimal]:
    deltas: dict[str, Decimal] = {}
    for code, current_rate in current_rates.items():
        previous_rate = previous_rates.get(code)
        if previous_rate is not None:
            deltas[code] = current_rate.unit_rate - previous_rate.unit_rate
    return deltas


class CBRService:
    BASE_URL = "https://www.cbr.ru/scripts/XML_daily.asp"

    def __init__(
        self,
        base_url: str = BASE_URL,
        timeout_seconds: int = 10,
        max_previous_lookup_days: int = 14,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.max_previous_lookup_days = max_previous_lookup_days

    async def fetch_rates(self, target_date: date) -> RatesSnapshot:
        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    self.base_url,
                    params={"date_req": target_date.strftime("%d/%m/%Y")},
                ) as response:
                    response.raise_for_status()
                    payload = await response.read()
        except Exception as exc:
            raise CBRServiceError("Could not fetch CBR rates") from exc

        return parse_cbr_xml(payload)

    async def fetch_previous_available(self, before_date: date) -> RatesSnapshot:
        cursor = before_date - timedelta(days=1)
        for _ in range(self.max_previous_lookup_days):
            snapshot = await self.fetch_rates(cursor)
            if snapshot.date < before_date:
                return snapshot
            cursor -= timedelta(days=1)
        raise CBRServiceError(f"Could not find CBR date before {before_date.isoformat()}")

    async def get_rates_with_delta(self, target_date: date) -> RatesSnapshot:
        current = await self.fetch_rates(target_date)
        previous = await self.fetch_previous_available(current.date)
        return RatesSnapshot(
            date=current.date,
            rates=current.rates,
            previous_date=previous.date,
            deltas=calculate_deltas(current.rates, previous.rates),
        )
