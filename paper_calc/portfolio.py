"""Pure weighted-average accounting for a paper portfolio."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Context, Decimal, localcontext
from typing import Final

from paper_calc.errors import (
    DuplicateTransactionError,
    InsufficientCashError,
    InsufficientPositionError,
    MissingPriceError,
    ValidationError,
)
from paper_calc.models import (
    DecimalInput,
    PortfolioReport,
    PositionReport,
    Transaction,
    _coerce_decimal,
    _require_positive,
)

_PRECISION: Final[int] = 28
_MONEY_QUANTUM: Final[Decimal] = Decimal("0.01")
_AVG_QUANTUM: Final[Decimal] = Decimal("0.0001")


@dataclass(slots=True)
class _Lot:
    """Open lot tracked at full precision.

    ``avg_cost`` is fixed at each buy (basis / quantity) and is not recomputed
    after a sell. The cost basis itself is reduced in proportion to the shares
    sold, which leaves ``avg_cost`` unchanged in exact arithmetic.
    """

    quantity: Decimal
    basis: Decimal
    avg_cost: Decimal


def _decimal_context() -> Context:
    return Context(prec=_PRECISION, rounding=ROUND_HALF_UP)


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _quantize_avg(value: Decimal) -> Decimal:
    return value.quantize(_AVG_QUANTUM, rounding=ROUND_HALF_UP)


def _as_transactions(transactions: Iterable[Transaction]) -> tuple[Transaction, ...]:
    if isinstance(transactions, (str, bytes)) or not isinstance(transactions, Iterable):
        raise TypeError(
            "transactions must be an iterable of Transaction, "
            f"not {type(transactions).__name__}"
        )
    materialized: list[Transaction] = []
    for index, item in enumerate(transactions):
        if not isinstance(item, Transaction):
            raise TypeError(
                f"transactions[{index}] must be Transaction, not {type(item).__name__}"
            )
        materialized.append(item)
    return tuple(materialized)


def _apply_buy(lots: dict[str, _Lot], cash: Decimal, tx: Transaction) -> Decimal:
    cost = tx.quantity * tx.price + tx.fee
    if cost > cash:
        raise InsufficientCashError(
            transaction_id=tx.id,
            ticker=tx.ticker,
            required=cost,
            available=cash,
        )
    updated_cash = cash - cost
    existing = lots.get(tx.ticker)
    if existing is None:
        lots[tx.ticker] = _Lot(
            quantity=tx.quantity,
            basis=cost,
            avg_cost=cost / tx.quantity,
        )
        return updated_cash
    new_quantity = existing.quantity + tx.quantity
    new_basis = existing.basis + cost
    existing.quantity = new_quantity
    existing.basis = new_basis
    existing.avg_cost = new_basis / new_quantity
    return updated_cash


def _apply_sell(
    lots: dict[str, _Lot],
    cash: Decimal,
    realized: Decimal,
    tx: Transaction,
) -> tuple[Decimal, Decimal]:
    existing = lots.get(tx.ticker)
    available = existing.quantity if existing is not None else Decimal("0")
    if existing is None or tx.quantity > existing.quantity:
        raise InsufficientPositionError(
            transaction_id=tx.id,
            ticker=tx.ticker,
            requested=tx.quantity,
            available=available,
        )
    updated_cash = cash + tx.quantity * tx.price - tx.fee
    updated_realized = realized + tx.quantity * (tx.price - existing.avg_cost) - tx.fee
    remaining = existing.quantity - tx.quantity
    if remaining == 0:
        del lots[tx.ticker]
        return updated_cash, updated_realized
    existing.basis = existing.basis * remaining / existing.quantity
    existing.quantity = remaining
    return updated_cash, updated_realized


def _resolve_prices(
    open_tickers: set[str],
    current_prices: Mapping[str, DecimalInput],
) -> dict[str, Decimal]:
    """Map each open ticker to one positive finite price.

    Keys are matched after ``strip().upper()``, the same normalization used
    for transaction tickers. Entries that do not name an open position are
    ignored, including any invalid values they may carry.
    """
    if not isinstance(current_prices, Mapping):
        raise TypeError(
            "current_prices must be a mapping of ticker to price, "
            f"not {type(current_prices).__name__}"
        )
    resolved: dict[str, Decimal] = {}
    for raw_key, raw_value in current_prices.items():
        if not isinstance(raw_key, str):
            continue
        ticker = raw_key.strip().upper()
        if ticker not in open_tickers:
            continue
        price = _require_positive(raw_value, field=f"current price for {ticker}")
        previous = resolved.get(ticker)
        if previous is not None and previous != price:
            raise ValidationError(
                f"Conflicting current prices for {ticker}: {previous} and {price}"
            )
        resolved[ticker] = price
    missing = tuple(sorted(open_tickers.difference(resolved)))
    if missing:
        raise MissingPriceError(missing)
    return resolved


def _build_report(
    lots: dict[str, _Lot],
    cash: Decimal,
    realized: Decimal,
    prices: Mapping[str, Decimal],
) -> PortfolioReport:
    rows: list[PositionReport] = []
    market_total = Decimal("0")
    unrealized_total = Decimal("0")
    for ticker in sorted(lots):
        lot = lots[ticker]
        market_price = prices[ticker]
        market_value = lot.quantity * market_price
        unrealized = market_value - lot.basis
        market_total += market_value
        unrealized_total += unrealized
        rows.append(
            PositionReport(
                ticker=ticker,
                quantity=lot.quantity,
                avg_cost=_quantize_avg(lot.avg_cost),
                market_price=_quantize_money(market_price),
                market_value=_quantize_money(market_value),
                unrealized_pnl=_quantize_money(unrealized),
            )
        )
    # Identities below hold on these full-precision totals, before output rounding:
    #   total_equity = cash + sum(market_value)
    #   total_equity = starting_cash + realized + unrealized
    return PortfolioReport(
        positions=tuple(rows),
        cash=_quantize_money(cash),
        realized_pnl=_quantize_money(realized),
        unrealized_pnl=_quantize_money(unrealized_total),
        total_equity=_quantize_money(cash + market_total),
    )


def calculate(
    transactions: Iterable[Transaction],
    current_prices: Mapping[str, DecimalInput],
    starting_cash: DecimalInput = Decimal("2000.00"),
) -> PortfolioReport:
    """Value a paper portfolio after applying ``transactions`` in order.

    The function is pure: it copies its inputs, keeps books in local
    variables, and either returns a complete report or raises. A repeated
    transaction id with the same normalized content is skipped. The same id
    with different content raises :class:`DuplicateTransactionError`.

    Money math runs in a local ``decimal`` context with precision 28 and
    ``ROUND_HALF_UP``. Only the returned report is quantized (money to 0.01,
    average cost to 0.0001).
    """
    orders = _as_transactions(transactions)
    cash = _coerce_decimal(starting_cash, field="starting_cash")
    seen: dict[str, Transaction] = {}
    lots: dict[str, _Lot] = {}
    realized = Decimal("0")

    with localcontext(_decimal_context()):
        for tx in orders:
            previous = seen.get(tx.id)
            if previous is not None:
                if previous != tx:
                    raise DuplicateTransactionError(tx.id)
                continue
            seen[tx.id] = tx
            if tx.side == "buy":
                cash = _apply_buy(lots, cash, tx)
            else:
                cash, realized = _apply_sell(lots, cash, realized, tx)
        prices = _resolve_prices(set(lots), current_prices)
        return _build_report(lots, cash, realized, prices)


__all__ = ["calculate"]
