import decimal
import math

import babel.numbers
import flask
import flask_babel

Money = decimal.Decimal | float | int


def format_money(amount: Money | None, currency: str) -> str:
    """Render a monetary amount in the configured currency.

    An empty currency yields a bare number with two decimals, which is what
    databases created before the currency setting existed carry.
    """
    if amount is None or (isinstance(amount, float) and math.isnan(amount)):
        return ""
    locale = (flask.has_request_context() and flask_babel.get_locale()) or "en_US"
    if currency:
        return babel.numbers.format_currency(amount, currency, locale=locale)
    return babel.numbers.format_decimal(amount, format="#,##0.00", locale=locale)


def money_title(label: str, currency: str) -> str:
    """Suffix a plot axis or tooltip label with the currency, as done for units."""
    return f"{label} / {currency}" if currency else label
