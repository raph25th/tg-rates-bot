from datetime import date
from decimal import Decimal

import pytest

from services.cbr import CBRService, CurrencyRate, calculate_deltas, parse_cbr_xml


SAMPLE_XML = """<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="26.04.2026" name="Foreign Currency Market">
    <Valute ID="R01235">
        <NumCode>840</NumCode>
        <CharCode>USD</CharCode>
        <Nominal>1</Nominal>
        <Name>Доллар США</Name>
        <Value>75,5273</Value>
    </Valute>
    <Valute ID="R01375">
        <NumCode>156</NumCode>
        <CharCode>CNY</CharCode>
        <Nominal>10</Nominal>
        <Name>Китайский юань</Name>
        <Value>104,7000</Value>
    </Valute>
</ValCurs>
"""


def test_parse_cbr_xml_normalizes_rates() -> None:
    snapshot = parse_cbr_xml(SAMPLE_XML)

    assert snapshot.date == date(2026, 4, 26)
    assert snapshot.rates["USD"].code == "USD"
    assert snapshot.rates["USD"].name == "Доллар США"
    assert snapshot.rates["USD"].nominal == 1
    assert snapshot.rates["USD"].value == Decimal("75.5273")
    assert snapshot.rates["USD"].unit_rate == Decimal("75.5273")
    assert snapshot.rates["CNY"].nominal == 10
    assert snapshot.rates["CNY"].unit_rate == Decimal("10.4700")


def test_calculate_deltas_uses_unit_rate() -> None:
    current = {
        "USD": CurrencyRate(
            code="USD",
            name="Доллар США",
            nominal=1,
            value=Decimal("75.5273"),
            unit_rate=Decimal("75.5273"),
            date=date(2026, 4, 26),
        ),
        "CNY": CurrencyRate(
            code="CNY",
            name="Китайский юань",
            nominal=10,
            value=Decimal("104.7000"),
            unit_rate=Decimal("10.4700"),
            date=date(2026, 4, 26),
        ),
    }
    previous = {
        "USD": CurrencyRate(
            code="USD",
            name="Доллар США",
            nominal=1,
            value=Decimal("74.8373"),
            unit_rate=Decimal("74.8373"),
            date=date(2026, 4, 25),
        ),
        "CNY": CurrencyRate(
            code="CNY",
            name="Китайский юань",
            nominal=10,
            value=Decimal("104.0000"),
            unit_rate=Decimal("10.4000"),
            date=date(2026, 4, 25),
        ),
    }

    assert calculate_deltas(current, previous) == {
        "USD": Decimal("0.6900"),
        "CNY": Decimal("0.0700"),
    }


@pytest.mark.asyncio
async def test_get_latest_cbr_rates_uses_cbr_response_date_without_date_req() -> None:
    class FakeCBRService(CBRService):
        def __init__(self) -> None:
            super().__init__()
            self.params = "not-called"

        async def _fetch_rates(self, params=None):
            self.params = params
            return parse_cbr_xml(SAMPLE_XML)

    service = FakeCBRService()

    snapshot = await service.get_latest_cbr_rates()

    assert service.params is None
    assert snapshot.date == date(2026, 4, 26)


@pytest.mark.asyncio
async def test_fetch_rates_uses_requested_date_req_but_keeps_response_date() -> None:
    class FakeCBRService(CBRService):
        def __init__(self) -> None:
            super().__init__()
            self.params = None

        async def _fetch_rates(self, params=None):
            self.params = params
            return parse_cbr_xml(SAMPLE_XML)

    service = FakeCBRService()

    snapshot = await service.fetch_rates(date(2026, 4, 30))

    assert service.params == {"date_req": "30/04/2026"}
    assert snapshot.date == date(2026, 4, 26)
