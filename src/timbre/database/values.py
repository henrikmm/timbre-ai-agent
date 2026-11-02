"""Exact value conversions shared by import and read interfaces."""

from decimal import Decimal, InvalidOperation, localcontext

SQLITE_MAX_INTEGER = 2**63 - 1


def scaled_integer(value: str | Decimal | int, *, maximum: int = SQLITE_MAX_INTEGER) -> int:
    """Scale by 100 exactly; reject floats, negatives, non-finite values, and rounding."""
    if isinstance(value, bool) or not isinstance(value, (str, Decimal, int)):
        raise ValueError("an exact decimal string, Decimal, or integer is required")
    try:
        amount = Decimal(value)
        if not amount.is_finite() or amount < 0:
            raise ValueError("a finite non-negative value is required")
        if amount > Decimal(maximum) / 100:
            raise ValueError("value exceeds the supported range")
        with localcontext() as context:
            context.prec = max(32, len(amount.as_tuple().digits) + 4)
            scaled = amount * 100
            if scaled != scaled.to_integral_value():
                raise ValueError("more than two non-zero decimal places are not supported")
            return int(scaled)
    except (InvalidOperation, TypeError, OverflowError) as error:
        raise ValueError("invalid decimal value") from error


def to_cents(value: str | Decimal | int) -> int:
    """Represent BRL without binary floating point."""
    return scaled_integer(value)


def from_cents(value: int) -> Decimal:
    """Return a BRL amount with two decimal places."""
    return (Decimal(value) / 100).quantize(Decimal("0.01"))
