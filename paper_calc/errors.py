"""Domain errors raised by the paper portfolio calculator."""

from __future__ import annotations

from decimal import Decimal


class PaperCalcError(Exception):
    """Base class for every error raised by :mod:`paper_calc`."""


class ValidationError(PaperCalcError):
    """A transaction, price, or cash amount violates a validation rule."""


class InsufficientCashError(PaperCalcError):
    """A buy, including its fee, costs more cash than the portfolio holds."""

    def __init__(
        self,
        *,
        transaction_id: str,
        ticker: str,
        required: Decimal,
        available: Decimal,
    ) -> None:
        self.transaction_id: str = transaction_id
        self.ticker: str = ticker
        self.required: Decimal = required
        self.available: Decimal = available
        super().__init__(
            f"Insufficient cash for transaction {transaction_id!r} buying {ticker}: "
            f"required {required}, available {available}"
        )


class InsufficientPositionError(PaperCalcError):
    """A sell asks for more shares than the portfolio currently holds."""

    def __init__(
        self,
        *,
        transaction_id: str,
        ticker: str,
        requested: Decimal,
        available: Decimal,
    ) -> None:
        self.transaction_id: str = transaction_id
        self.ticker: str = ticker
        self.requested: Decimal = requested
        self.available: Decimal = available
        super().__init__(
            f"Insufficient position for transaction {transaction_id!r} selling {ticker}: "
            f"requested {requested}, available {available}"
        )


class DuplicateTransactionError(PaperCalcError):
    """The same transaction id was submitted again with different content."""

    def __init__(self, transaction_id: str) -> None:
        self.transaction_id: str = transaction_id
        super().__init__(
            f"Transaction id {transaction_id!r} was reused with different content"
        )


class MissingPriceError(PaperCalcError):
    """One or more open positions have no current price."""

    def __init__(self, tickers: tuple[str, ...]) -> None:
        if not tickers:
            raise ValueError("tickers must not be empty")
        self.tickers: tuple[str, ...] = tickers
        self.ticker: str = tickers[0]
        joined = ", ".join(tickers)
        super().__init__(f"Missing current price for open position(s): {joined}")


__all__ = [
    "DuplicateTransactionError",
    "InsufficientCashError",
    "InsufficientPositionError",
    "MissingPriceError",
    "PaperCalcError",
    "ValidationError",
]
