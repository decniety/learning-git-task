"""Pytest coverage for the paper portfolio calculator."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import ROUND_DOWN, Decimal, getcontext
from typing import cast

import pytest

from paper_calc import (
    DuplicateTransactionError,
    InsufficientCashError,
    InsufficientPositionError,
    MissingPriceError,
    PortfolioReport,
    PositionReport,
    Transaction,
    ValidationError,
    calculate,
)
from paper_calc.models import DecimalInput, Side

_ONE = Decimal("1")
_ZERO = Decimal("0")


def _tx(
    id: str,
    ticker: str = "AAA",
    side: Side = "buy",
    quantity: DecimalInput = "1",
    price: DecimalInput = "10",
    fee: DecimalInput = "0",
) -> Transaction:
    return Transaction(
        id=id,
        ticker=ticker,
        side=side,
        quantity=quantity,
        price=price,
        fee=fee,
    )


def _prices(*items: tuple[str, DecimalInput]) -> dict[str, DecimalInput]:
    return dict(items)


def test_single_buy() -> None:
    report = calculate(
        [_tx("1", ticker="AAPL", quantity="2", price="10")],
        _prices(("AAPL", Decimal("12"))),
        Decimal("2000.00"),
    )
    assert report == PortfolioReport(
        positions=(
            PositionReport(
                ticker="AAPL",
                quantity=Decimal("2"),
                avg_cost=Decimal("10.0000"),
                market_price=Decimal("12.00"),
                market_value=Decimal("24.00"),
                unrealized_pnl=Decimal("4.00"),
            ),
        ),
        cash=Decimal("1980.00"),
        realized_pnl=Decimal("0.00"),
        unrealized_pnl=Decimal("4.00"),
        total_equity=Decimal("2004.00"),
    )


def test_weighted_average_multiple_buys() -> None:
    report = calculate(
        [
            _tx("1", quantity="2", price="10"),
            _tx("2", quantity="2", price="20"),
        ],
        _prices(("AAA", Decimal("15"))),
        Decimal("2000"),
    )
    position = report.positions[0]
    assert position.quantity == Decimal("4")
    assert position.avg_cost == Decimal("15.0000")
    assert position.market_value == Decimal("60.00")
    assert position.unrealized_pnl == Decimal("0.00")
    assert report.cash == Decimal("1940.00")
    assert report.total_equity == Decimal("2000.00")


def test_partial_and_full_sell_realized_pnl() -> None:
    partial = calculate(
        [
            _tx("1", quantity="10", price="10"),
            _tx("2", side="sell", quantity="4", price="12"),
        ],
        _prices(("AAA", Decimal("11"))),
        Decimal("2000.00"),
    )
    assert partial.positions[0].quantity == Decimal("6")
    assert partial.positions[0].avg_cost == Decimal("10.0000")
    assert partial.realized_pnl == Decimal("8.00")
    assert partial.unrealized_pnl == Decimal("6.00")
    assert partial.cash == Decimal("1948.00")
    assert partial.total_equity == Decimal("2014.00")

    closed = calculate(
        [
            _tx("1", quantity="10", price="10"),
            _tx("2", side="sell", quantity="4", price="12"),
            _tx("3", side="sell", quantity="6", price="11"),
        ],
        {},
        Decimal("2000.00"),
    )
    assert closed.positions == ()
    assert closed.realized_pnl == Decimal("14.00")
    assert closed.unrealized_pnl == Decimal("0.00")
    assert closed.cash == Decimal("2014.00")
    assert closed.total_equity == Decimal("2014.00")


def test_fees_included_in_cost_basis_cash_and_realized() -> None:
    opened = calculate(
        [_tx("1", quantity="10", price="10", fee="5")],
        _prices(("AAA", Decimal("10"))),
        Decimal("2000"),
    )
    assert opened.positions[0].avg_cost == Decimal("10.5000")
    assert opened.cash == Decimal("1895.00")
    assert opened.unrealized_pnl == Decimal("-5.00")
    assert opened.total_equity == Decimal("1995.00")

    closed = calculate(
        [
            _tx("1", quantity="10", price="10", fee="5"),
            _tx("2", side="sell", quantity="10", price="10", fee="2"),
        ],
        {},
        Decimal("2000"),
    )
    assert closed.positions == ()
    assert closed.realized_pnl == Decimal("-7.00")
    assert closed.cash == Decimal("1993.00")
    assert closed.total_equity == Decimal("1993.00")


def test_insufficient_cash() -> None:
    prices = _prices(("AAA", Decimal("1")))
    with pytest.raises(InsufficientCashError) as exact:
        calculate(
            [_tx("1", quantity="1", price="2000.01")],
            prices,
            Decimal("2000.00"),
        )
    assert exact.value.required == Decimal("2000.01")
    assert exact.value.available == Decimal("2000.00")

    affordable = calculate(
        [_tx("1", quantity="1", price="2000")],
        prices,
        Decimal("2000.00"),
    )
    assert affordable.cash == Decimal("0.00")
    assert affordable.positions[0].quantity == _ONE


def test_insufficient_cash_includes_fee() -> None:
    with pytest.raises(InsufficientCashError):
        calculate(
            [_tx("1", quantity="100", price="19", fee="101")],
            _prices(("AAA", Decimal("19"))),
            Decimal("2000"),
        )
    fits = calculate(
        [_tx("1", quantity="100", price="19", fee="100")],
        _prices(("AAA", Decimal("19"))),
        Decimal("2000"),
    )
    assert fits.cash == Decimal("0.00")


def test_insufficient_position() -> None:
    with pytest.raises(InsufficientPositionError) as naked:
        calculate(
            [_tx("1", side="sell", quantity="1", price="10")],
            {},
            Decimal("2000"),
        )
    assert naked.value.available == _ZERO
    assert naked.value.requested == _ONE

    with pytest.raises(InsufficientPositionError) as over:
        calculate(
            [
                _tx("1", quantity="5", price="10"),
                _tx("2", side="sell", quantity="5.0001", price="10"),
            ],
            _prices(("AAA", Decimal("10"))),
            Decimal("2000"),
        )
    assert over.value.available == Decimal("5")
    assert over.value.ticker == "AAA"

    closed = calculate(
        [
            _tx("1", quantity="5", price="10"),
            _tx("2", side="sell", quantity="5", price="10"),
        ],
        {},
        Decimal("2000"),
    )
    assert closed.positions == ()
    assert closed.cash == Decimal("2000.00")


def test_rejects_float() -> None:
    with pytest.raises(TypeError):
        _tx("1", quantity=cast(DecimalInput, 1.5))
    with pytest.raises(TypeError):
        _tx("1", price=cast(DecimalInput, 10.0))
    with pytest.raises(TypeError):
        _tx("1", fee=cast(DecimalInput, 0.1))
    with pytest.raises(TypeError):
        _tx("1", quantity=cast(DecimalInput, True))
    valid = _tx("1", quantity="1", price="10")
    with pytest.raises(TypeError):
        calculate([valid], _prices(("AAA", Decimal("10"))), cast(DecimalInput, 2000.0))
    with pytest.raises(TypeError):
        calculate([valid], {"AAA": cast(DecimalInput, 10.5)}, Decimal("2000"))


@pytest.mark.parametrize(
    ("quantity", "price", "fee"),
    [
        ("0", "10", "0"),
        ("-1", "10", "0"),
        (0, "10", "0"),
        (-5, "10", "0"),
        (Decimal("-0"), "10", "0"),
        ("1", "0", "0"),
        ("1", "-2", "0"),
        ("1", Decimal("0.00"), "0"),
        ("1", "10", "-0.01"),
        ("1", "10", -1),
    ],
)
def test_rejects_non_positive_and_negative_amounts(
    quantity: DecimalInput,
    price: DecimalInput,
    fee: DecimalInput,
) -> None:
    with pytest.raises(ValidationError):
        _tx("1", quantity=quantity, price=price, fee=fee)


@pytest.mark.parametrize(
    ("quantity", "price", "fee"),
    [
        (Decimal("NaN"), "1", "0"),
        ("NaN", "1", "0"),
        (Decimal("sNaN"), "1", "0"),
        ("1", Decimal("Infinity"), "0"),
        ("1", "-Infinity", "0"),
        ("1", "Infinity", "0"),
        ("1", "1", Decimal("-Infinity")),
        ("1", "1", "NaN"),
    ],
)
def test_rejects_nan_and_infinity(
    quantity: DecimalInput,
    price: DecimalInput,
    fee: DecimalInput,
) -> None:
    with pytest.raises(ValidationError):
        _tx("1", quantity=quantity, price=price, fee=fee)

    with pytest.raises(ValidationError):
        calculate([], {}, Decimal("NaN"))
    with pytest.raises(ValidationError):
        calculate(
            [_tx("1")],
            _prices(("AAA", Decimal("Infinity"))),
            Decimal("100"),
        )


@pytest.mark.parametrize(
    "ticker",
    ["", "   ", "123", "123ABC", "ABCDEFGHIJK", "AAPL!", "-ABC", ".ABC", "AA PL"],
)
def test_rejects_bad_ticker(ticker: str) -> None:
    with pytest.raises(ValidationError):
        _tx("1", ticker=ticker)


@pytest.mark.parametrize("side", ["BUY", "Sell", "hold", "", None, 1])
def test_rejects_invalid_side(side: object) -> None:
    with pytest.raises(ValidationError):
        Transaction("1", "AAA", cast(Side, side), "1", "10")


def test_ticker_normalization_and_price_key_case() -> None:
    transaction = _tx("1", ticker="  brk.b  ", quantity=2, price="15.5", fee=0)
    assert transaction.ticker == "BRK.B"
    report = calculate(
        [transaction],
        {" brk.b ": "16"},
        100,
    )
    assert report.positions[0].ticker == "BRK.B"
    assert report.positions[0].quantity == Decimal("2")
    assert report.positions[0].avg_cost == Decimal("15.5000")
    assert report.positions[0].market_price == Decimal("16.00")
    assert report.cash == Decimal("69.00")
    assert report.unrealized_pnl == Decimal("1.00")
    assert report.total_equity == Decimal("101.00")

    edge = _tx("2", ticker="abcdefghij")
    assert edge.ticker == "ABCDEFGHIJ"
    dotted = _tx("3", ticker="brk-b")
    assert dotted.ticker == "BRK-B"


def test_duplicate_id_identical_is_noop() -> None:
    starting = Decimal("10")
    prices = _prices(("AAPL", Decimal("10")))
    once = calculate(
        [Transaction("1", "aapl", "buy", Decimal("1.0"), "10.00", 0)],
        prices,
        starting,
    )
    twice = calculate(
        [
            Transaction("1", "aapl", "buy", Decimal("1.0"), "10.00", 0),
            Transaction("1", "AAPL", "buy", "1", Decimal("10"), "0.0"),
        ],
        prices,
        starting,
    )
    assert twice == once
    assert twice.positions[0].quantity == _ONE
    assert twice.cash == Decimal("0.00")


def test_duplicate_id_different_content_raises() -> None:
    prices = _prices(("AAA", Decimal("10")))
    base = _tx("1", quantity="1", price="10")
    variants = [
        _tx("1", quantity="2", price="10"),
        _tx("1", quantity="1", price="11"),
        _tx("1", quantity="1", price="10", fee="0.01"),
        _tx("1", ticker="BBB", quantity="1", price="10"),
        _tx("1", side="sell", quantity="1", price="10"),
    ]
    for other in variants:
        with pytest.raises(DuplicateTransactionError) as caught:
            calculate([base, other], prices, Decimal("100"))
        assert caught.value.transaction_id == "1"


def test_missing_price() -> None:
    with pytest.raises(MissingPriceError) as missing:
        calculate(
            [_tx("1", ticker="msft")],
            _prices(("AAPL", Decimal("10"))),
            Decimal("2000"),
        )
    assert missing.value.ticker == "MSFT"
    assert missing.value.tickers == ("MSFT",)

    with pytest.raises(MissingPriceError) as several:
        calculate(
            [
                _tx("1", ticker="MMM"),
                _tx("2", ticker="AAA"),
            ],
            _prices(("ZZZ", Decimal("1"))),
            Decimal("5000"),
        )
    assert several.value.ticker == "AAA"
    assert several.value.tickers == ("AAA", "MMM")


def test_prices_without_positions_are_ignored() -> None:
    report = calculate(
        [
            _tx("1", ticker="AAA", quantity="1", price="10"),
            _tx("2", ticker="AAA", side="sell", quantity="1", price="12"),
        ],
        {
            "AAA": Decimal("999"),
            "ZZZ": Decimal("1"),
            "nope": cast(DecimalInput, 1.5),
        },
        Decimal("2000"),
    )
    assert report.positions == ()
    assert report.realized_pnl == Decimal("2.00")
    assert report.cash == Decimal("2002.00")


def test_conflicting_normalized_prices_are_rejected() -> None:
    with pytest.raises(ValidationError):
        calculate(
            [_tx("1", ticker="AAA")],
            {"aaa": Decimal("10"), "AAA": Decimal("11")},
            Decimal("100"),
        )
    with pytest.raises(ValidationError):
        calculate(
            [_tx("1")],
            _prices(("AAA", Decimal("0"))),
            Decimal("100"),
        )
    with pytest.raises(ValidationError):
        calculate(
            [_tx("1")],
            _prices(("AAA", Decimal("-1"))),
            Decimal("100"),
        )


def test_point_one_plus_point_two_is_exactly_thirty_cents() -> None:
    report = calculate(
        [
            _tx("1", ticker="AAA", quantity="1", price="0.1"),
            _tx("2", ticker="BBB", quantity="1", price="0.2"),
        ],
        _prices(("AAA", Decimal("0.1")), ("BBB", Decimal("0.2"))),
        Decimal("1.00"),
    )
    assert report.cash == Decimal("0.70")
    assert Decimal("1.00") - report.cash == Decimal("0.30")
    assert report.total_equity == Decimal("1.00")

    single = calculate(
        [_tx("1", quantity="1", price="0.1", fee="0.2")],
        _prices(("AAA", Decimal("0.1"))),
        Decimal("1.00"),
    )
    assert single.positions[0].avg_cost == Decimal("0.3000")
    assert single.cash == Decimal("0.70")


def test_fractional_shares() -> None:
    report = calculate(
        [_tx("1", quantity="0.3333", price="2")],
        _prices(("AAA", Decimal("2"))),
        Decimal("10"),
    )
    position = report.positions[0]
    assert position.quantity == Decimal("0.3333")
    assert position.quantity.as_tuple().exponent == -4
    assert position.avg_cost == Decimal("2.0000")
    assert position.market_value == Decimal("0.67")
    assert position.unrealized_pnl == Decimal("0.00")
    assert report.cash == Decimal("9.33")
    assert report.total_equity == Decimal("10.00")


def test_output_rounding_half_up() -> None:
    marked = calculate(
        [_tx("1", quantity="1", price="1")],
        _prices(("AAA", Decimal("1.015"))),
        Decimal("2000"),
    )
    assert marked.positions[0].market_price == Decimal("1.02")
    assert marked.positions[0].market_value == Decimal("1.02")
    assert marked.positions[0].unrealized_pnl == Decimal("0.02")
    assert marked.cash == Decimal("1999.00")
    assert marked.total_equity == Decimal("2000.02")
    assert marked.cash.as_tuple().exponent == -2
    assert marked.positions[0].avg_cost.as_tuple().exponent == -4

    averaged = calculate(
        [_tx("1", quantity="1", price="1.00015")],
        _prices(("AAA", Decimal("1.00015"))),
        Decimal("10"),
    )
    assert averaged.positions[0].avg_cost == Decimal("1.0002")


def test_equity_invariant() -> None:
    starting = Decimal("2000.00")
    report = calculate(
        [
            _tx("1", ticker="AAA", quantity="10", price="10", fee="0"),
            _tx("2", ticker="BBB", quantity="2", price="10.50", fee="0.50"),
            _tx("3", ticker="AAA", side="sell", quantity="4", price="12", fee="0"),
        ],
        _prices(("AAA", Decimal("11")), ("BBB", Decimal("11.25"))),
        starting,
    )
    market_sum = sum((position.market_value for position in report.positions), Decimal("0"))
    assert report.total_equity == report.cash + market_sum
    assert report.total_equity == starting + report.realized_pnl + report.unrealized_pnl
    assert report.realized_pnl == Decimal("8.00")
    assert report.unrealized_pnl == Decimal("7.00")
    assert report.cash == Decimal("1926.50")
    assert report.total_equity == Decimal("2015.00")
    assert [position.ticker for position in report.positions] == ["AAA", "BBB"]


def test_positions_sorted_by_ticker() -> None:
    report = calculate(
        [
            _tx("1", ticker="MMM", price="1"),
            _tx("2", ticker="AAA", price="1"),
            _tx("3", ticker="ZZZ", price="1"),
        ],
        _prices(
            ("ZZZ", Decimal("1")),
            ("MMM", Decimal("1")),
            ("AAA", Decimal("1")),
        ),
        Decimal("100"),
    )
    assert [position.ticker for position in report.positions] == ["AAA", "MMM", "ZZZ"]


def test_closed_position_reopens_with_fresh_basis() -> None:
    report = calculate(
        [
            _tx("1", quantity="1", price="10"),
            _tx("2", side="sell", quantity="1", price="12"),
            _tx("3", quantity="1", price="30"),
        ],
        _prices(("AAA", Decimal("30"))),
        Decimal("2000"),
    )
    assert len(report.positions) == 1
    assert report.positions[0].avg_cost == Decimal("30.0000")
    assert report.positions[0].quantity == _ONE
    assert report.realized_pnl == Decimal("2.00")
    assert report.unrealized_pnl == Decimal("0.00")
    assert report.cash == Decimal("1972.00")
    assert report.total_equity == Decimal("2002.00")


def test_atomicity_on_error() -> None:
    first = _tx("1", quantity="1", price="10")
    second = _tx("2", quantity="1", price="10")
    third = _tx("3", quantity="1", price="3000")
    orders = [first, second, third]
    snapshot = list(orders)
    prices: dict[str, DecimalInput] = {"AAA": Decimal("10"), "EXTRA": Decimal("1")}
    price_snapshot: Mapping[str, DecimalInput] = dict(prices)

    with pytest.raises(InsufficientCashError):
        calculate(orders, prices, Decimal("2000"))

    assert orders == snapshot
    assert orders[0] is first
    assert orders[1] is second
    assert orders[2] is third
    assert prices == price_snapshot

    applied = calculate(orders[:2], prices, Decimal("2000"))
    assert applied.cash == Decimal("1980.00")
    assert applied.positions[0].quantity == Decimal("2")

    with pytest.raises(InsufficientPositionError):
        calculate(
            [
                _tx("1", quantity="1", price="10"),
                _tx("2", side="sell", quantity="5", price="10"),
            ],
            prices,
            Decimal("2000"),
        )
    with pytest.raises(MissingPriceError):
        calculate([_tx("1", ticker="MSFT")], {}, Decimal("2000"))
    with pytest.raises(DuplicateTransactionError):
        calculate(
            [_tx("1", price="10"), _tx("1", price="11")],
            prices,
            Decimal("2000"),
        )


def test_default_starting_cash_and_empty_book() -> None:
    report = calculate([], {})
    assert report == PortfolioReport(
        positions=(),
        cash=Decimal("2000.00"),
        realized_pnl=Decimal("0.00"),
        unrealized_pnl=Decimal("0.00"),
        total_equity=Decimal("2000.00"),
    )


def test_does_not_depend_on_global_decimal_context() -> None:
    original_prec = getcontext().prec
    original_rounding = getcontext().rounding
    try:
        getcontext().prec = 2
        getcontext().rounding = ROUND_DOWN
        report = calculate(
            [_tx("1", quantity="3", price="10.19")],
            _prices(("AAA", Decimal("10.19"))),
            Decimal("100"),
        )
        assert report.positions[0].avg_cost == Decimal("10.1900")
        assert report.positions[0].market_value == Decimal("30.57")
        assert report.cash == Decimal("69.43")
        assert report.unrealized_pnl == Decimal("0.00")
        assert report.total_equity == Decimal("100.00")
    finally:
        getcontext().prec = original_prec
        getcontext().rounding = original_rounding
    assert getcontext().prec == original_prec
    assert getcontext().rounding == original_rounding


def test_no_global_state_between_calls() -> None:
    orders = [_tx("1", quantity="1", price="10")]
    prices = _prices(("AAA", Decimal("12")))
    first = calculate(orders, prices)
    second = calculate(orders, prices)
    assert first == second
    assert first.cash == Decimal("1990.00")


def test_transaction_is_frozen() -> None:
    transaction = _tx("1")
    with pytest.raises(AttributeError):
        setattr(transaction, "quantity", Decimal("2"))
    report = calculate([transaction], _prices(("AAA", Decimal("10"))), Decimal("100"))
    with pytest.raises(AttributeError):
        setattr(report, "cash", Decimal("0"))
    with pytest.raises(AttributeError):
        setattr(report.positions[0], "ticker", "ZZZ")


def test_rejects_non_transaction_and_bad_decimal_string() -> None:
    with pytest.raises(TypeError):
        calculate(cast(list[Transaction], [object()]), {}, Decimal("10"))
    with pytest.raises(TypeError):
        _tx("1", ticker=cast(str, 123))
    with pytest.raises(ValidationError):
        _tx("1", quantity="not-a-number")
    with pytest.raises(ValidationError):
        Transaction("", "AAA", "buy", "1", "10")
    with pytest.raises(TypeError):
        Transaction(cast(str, 1), "AAA", "buy", "1", "10")
