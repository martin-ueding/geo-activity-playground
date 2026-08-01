import decimal

import pytest
from flask import Flask

from geo_activity_playground.core.config import ConfigAccessor
from geo_activity_playground.core.currency import format_money, money_title


@pytest.mark.usefixtures("app_context")
def test_format_money_without_currency_stays_bare() -> None:
    assert format_money(decimal.Decimal("1234.5"), "") == "1,234.50"


@pytest.mark.usefixtures("app_context")
def test_format_money_uses_currency() -> None:
    assert "1,234.50" in format_money(decimal.Decimal("1234.5"), "EUR")
    assert "€" in format_money(decimal.Decimal("1234.5"), "EUR")


@pytest.mark.usefixtures("app_context")
def test_format_money_handles_missing_values() -> None:
    assert format_money(None, "EUR") == ""
    assert format_money(float("nan"), "EUR") == ""


def test_money_title_appends_currency() -> None:
    assert money_title("Cost", "EUR") == "Cost / EUR"
    assert money_title("Cost", "") == "Cost"


def test_currency_setting_round_trip(app: Flask) -> None:
    client = app.test_client()
    with app.app_context():
        assert ConfigAccessor().ui().currency == ""

    response = client.post("/settings/currency", data={"currency": "chf"})
    assert response.status_code == 302
    with app.app_context():
        assert ConfigAccessor().ui().currency == "CHF"


def test_currency_setting_rejects_unknown_code(app: Flask) -> None:
    client = app.test_client()
    client.post("/settings/currency", data={"currency": "XYZ"})
    with app.app_context():
        assert ConfigAccessor().ui().currency == ""
