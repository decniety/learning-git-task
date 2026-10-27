"""Frozen value objects for paper transactions and portfolio reports."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final, Literal

from paper_calc.errors import ValidationError

Side = Literal["buy", "sell"]
DecimalInput = Decimal | int | str

_TICKER_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Z][A-Z0-9.\-]{0,9}$")
_SIDES: Final[frozenset[str]] = frozenset({"buy", "sell"})


def _coerce_decimal(value: object, *, field: str) -> Decimal:
    """Convert ``Decimal``, ``int``, or ``str`` into a finite ``Decimal``.

    ``float`` is rejected, including ``bool`` (an ``int`` subclass), so money
    never passes through binary floating point.
    """
    if isinstance(value, bool) or isinstance(value, float):
        raise TypeError(
            f"{field} does not accept {type(value).__name__}; use Decimal, int, or str"
        )
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int):
        number = Decimal(value)
    elif isinstance(value, str):
        try:
            number = Decimal(value.strip())
        except InvalidOperation as exc:
            raise ValidationError(
                f"{field} is not a valid decimal: {value!r}"
            ) from exc
    else:
        raise TypeError(
            f"{field} must be Decimal, int, or str, not {type(value).__name__}"
        )
    if not number.is_finite():
        raise ValidationError(f"{field} must be a finite number, got {value!r}")
    return number


def _validate_id(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"id must be str, not {type(value).__name__}"
        )
    if value == "":
        raise ValidationError("transaction id must be a non-empty string")
    return value


def _normalize_ticker(value: object) -> str:
    if not isinstance(value, str):
        raise TypeError(
            f"ticker must be str, not {type(value).__name__}"
        )
    normalized = value.strip().upper()
    if _TICKER_PATTERN.fullmatch(normalized) is None:
        raise ValidationError(
            f"ticker {value!r} is invalid; after trim and uppercase it must match "
            r"^[A-Z][A-Z0-9.\-]{0,9}$"
        )
    return normalized


def _validate_side(value: object) -> Side:
    if value not in _SIDES:
        raise ValidationError(f"side must be 'buy' or 'sell', got {value!r}")
    if value == "buy":
        return "buy"
    return "sell"


def _require_positive(value: object, *, field: str) -> Decimal:
    number = _coerce_decimal(value, field=field)
    if number <= 0:
        raise ValidationError(f"{field} must be greater than 0, got {number}")
    return number


def _require_non_negative(value: object, *, field: str) -> Decimal:
    number = _coerce_decimal(value, field=field)
    if number < 0:
        raise ValidationError(f"{field} must be greater than or equal to 0, got {number}")
    return number


@dataclass(frozen=True, slots=True)
class Transaction:
    """One filled paper order.

    ``id`` is the idempotency key. ``ticker`` is stored normalized
    (trimmed, upper case). Quantity, price, and fee are stored as ``Decimal``.
    """

    id: str
    ticker: str
    side: Side
    quantity: Decimal
    price: Decimal
    fee: Decimal = Decimal("0")

    def __init__(
        self,
        id: str,
        ticker: str,
        side: Side,
        quantity: DecimalInput,
        price: DecimalInput,
        fee: DecimalInput = Decimal("0"),
    ) -> None:
        object.__setattr__(self, "id", _validate_id(id))
        object.__setattr__(self, "ticker", _normalize_ticker(ticker))
        object.__setattr__(self, "side", _validate_side(side))
        object.__setattr__(self, "quantity", _require_positive(quantity, field="quantity"))
        object.__setattr__(self, "price", _require_positive(price, field="price"))
        object.__setattr__(self, "fee", _require_non_negative(fee, field="fee"))


@dataclass(frozen=True, slots=True)
class PositionReport:
    """Valuation of one open position.

    Monetary fields are already rounded for output. ``quantity`` keeps the
    full working precision. ``avg_cost`` is rounded to 0.0001; the other
    money fields are rounded to 0.01.
    """

    ticker: str
    quantity: Decimal
    avg_cost: Decimal
    market_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal


@dataclass(frozen=True, slots=True)
class PortfolioReport:
    """Snapshot of cash, PnL, and open positions sorted by ticker."""

    positions: tuple[PositionReport, ...]
    cash: Decimal
    realized_pnl: Decimal
    unrealized_pnl: Decimal
    total_equity: Decimal


__all__ = [
    "DecimalInput",
    "PortfolioReport",
    "PositionReport",
    "Side",
    "Transaction",
]
