from decimal import Decimal, InvalidOperation
from typing import Any


class CatalogError(ValueError):
    pass


def _string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise CatalogError(f"{field} must be a non-empty string")
    return value


def _positive_int(value: Any, field: str) -> int:
    if type(value) is not int or value <= 0:
        raise CatalogError(f"{field} must be a positive integer")
    return value


def _decimal(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise CatalogError(f"{field} must be a decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as ex:
        raise CatalogError(f"{field} must be a decimal string") from ex
    if not parsed.is_finite() or parsed < 0:
        raise CatalogError(f"{field} must be a non-negative decimal string")
    return value
