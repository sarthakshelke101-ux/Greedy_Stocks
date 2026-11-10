"""Corporate-action adjusted historical price calculations.

Raw NSE prices are never modified.
Verified split and bonus adjustments are applied to pre-ex-date prices only.
This is a split/bonus-adjusted price series, NOT a total-return series.
"""

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

import numpy as np
import pandas as pd


SUPPORTED_ACTIONS = {"STOCK_SPLIT", "BONUS"}


def _parse_ratio(ratio: str) -> tuple[Decimal, Decimal]:
    """Parse a positive finite ratio such as '2:1' or '1:2'."""
    try:
        left, right = str(ratio).split(":")
        numerator = Decimal(left.strip())
        denominator = Decimal(right.strip())
    except (ValueError, InvalidOperation):
        raise ValueError(f"Invalid corporate-action ratio: {ratio!r}") from None

    if (
        not numerator.is_finite()
        or not denominator.is_finite()
        or numerator <= 0
        or denominator <= 0
    ):
        raise ValueError(f"Ratio values must be positive and finite: {ratio!r}")

    return numerator, denominator


def action_adjustment_factor(action: Mapping[str, Any]) -> Decimal:
    """Return the historical price conversion factor for one action."""
    if not isinstance(action, Mapping):
        raise ValueError("Corporate action must be a mapping.")

    action_type_value = action.get("action_type")
    if action_type_value is None or not str(action_type_value).strip():
        raise ValueError("Corporate action is missing action_type.")

    action_type = str(action_type_value).strip().upper()
    if action_type not in SUPPORTED_ACTIONS:
        raise ValueError(
            f"Unsupported action type {action_type!r}. "
            "Only verified splits and bonuses are supported."
        )

    if "ratio" not in action or action["ratio"] is None:
        raise ValueError("Corporate action is missing ratio.")

    numerator, denominator = _parse_ratio(action["ratio"])

    if action_type == "STOCK_SPLIT":
        return numerator / denominator

    # Bonus ratio 4:1 means 4 additional shares for each 1 held.
    # Total shares become 5, so the historical price factor is 5.
    return Decimal("1") + (numerator / denominator)


def _normalise_date(value: Any, field_name: str) -> pd.Timestamp:
    """Parse a date and normalize it to a timezone-naive calendar date."""
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f"Invalid {field_name}: {value!r}") from None

    if pd.isna(parsed):
        raise ValueError(f"Invalid {field_name}: {value!r}")

    if parsed.tzinfo is not None:
        raise ValueError(f"{field_name} must not contain a timezone: {value!r}")

    return parsed.normalize()


def build_adjusted_prices(
    prices: pd.DataFrame,
    actions: list[dict[str, Any]],
    date_col: str = "trade_date",
    price_col: str = "close",
) -> pd.DataFrame:
    """Build a separate split/bonus-adjusted price series.

    For every action, historical prices strictly before its ex-date
    are divided by that action's adjustment factor.

    Missing prices remain missing. Invalid non-missing prices are rejected.

    Returns original columns plus:
      - adjustment_factor
      - adjusted_close
    """
    if not isinstance(prices, pd.DataFrame):
        raise ValueError("prices must be a pandas DataFrame.")

    if date_col not in prices.columns:
        raise ValueError(f"Missing date column: {date_col}")

    if price_col not in prices.columns:
        raise ValueError(f"Missing price column: {price_col}")

    if not isinstance(actions, list):
        raise ValueError("actions must be a list of corporate-action mappings.")

    result = prices.copy(deep=True)

    try:
        parsed_dates = pd.to_datetime(result[date_col], errors="raise")
    except (TypeError, ValueError, OverflowError):
        raise ValueError("Invalid trading date found in price input.") from None

    if parsed_dates.isna().any():
        raise ValueError("Missing or invalid trading date found in price input.")

    # NSE trading dates are calendar dates; discard any time component.
    if getattr(parsed_dates.dt, "tz", None) is not None:
        raise ValueError("Trading dates must not contain a timezone.")

    result[date_col] = parsed_dates.dt.normalize()

    if result[date_col].duplicated().any():
        raise ValueError("Duplicate trading dates found in price input.")

    original_prices = result[price_col]
    numeric_prices = pd.to_numeric(original_prices, errors="coerce")

    invalid_conversion = original_prices.notna() & numeric_prices.isna()
    if invalid_conversion.any():
        raise ValueError("Non-numeric prices found in price input.")

    numeric_array = numeric_prices.to_numpy(dtype="float64", na_value=np.nan)
    finite_or_missing = np.isfinite(numeric_array) | np.isnan(numeric_array)
    if not finite_or_missing.all():
        raise ValueError("Infinite prices found in price input.")

    if (numeric_prices.dropna() <= 0).any():
        raise ValueError("Non-positive prices found in price input.")

    result[price_col] = numeric_prices

    prepared_actions: list[tuple[pd.Timestamp, float]] = []
    for action in actions:
        if not isinstance(action, Mapping):
            raise ValueError("Each corporate action must be a mapping.")

        if "ex_date" not in action or action["ex_date"] is None:
            raise ValueError("Corporate action is missing ex_date.")

        ex_date = _normalise_date(action["ex_date"], "corporate-action ex_date")
        decimal_factor = action_adjustment_factor(action)

        if not decimal_factor.is_finite() or decimal_factor <= 0:
            raise ValueError("Corporate-action factor must be positive and finite.")

        factor = float(decimal_factor)
        if not np.isfinite(factor) or factor <= 0:
            raise ValueError("Corporate-action factor is outside supported numeric range.")

        prepared_actions.append((ex_date, factor))

    # Use positional arrays so duplicate DataFrame index labels cannot
    # accidentally multiply or misalign adjustment factors.
    trading_dates = result[date_col]
    factors = np.ones(len(result), dtype="float64")

    for ex_date, factor in prepared_actions:
        historical_mask = (trading_dates < ex_date).to_numpy()
        factors[historical_mask] *= factor

    result["adjustment_factor"] = factors
    result["adjusted_close"] = numeric_prices.to_numpy(dtype="float64", na_value=np.nan) / factors

    result.attrs["price_basis"] = "SPLIT_BONUS_ADJUSTED"
    result.attrs["raw_price_basis"] = "RAW_CLOSE_UNADJUSTED"
    result.attrs["total_return"] = False

    return result.sort_values(date_col, kind="stable").reset_index(drop=True)
