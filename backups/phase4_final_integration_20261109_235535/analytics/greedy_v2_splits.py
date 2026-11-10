"""Chronological train/validation/test splits for Greedy V2."""

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DataSplits:
    train: pd.DataFrame
    validation: pd.DataFrame
    test: pd.DataFrame
    metadata: dict


def chronological_split(
    prices: pd.DataFrame,
    train_fraction: float = 0.60,
    validation_fraction: float = 0.20,
    allow_sparse_evaluation: bool = False,
) -> DataSplits:
    """Chronological split; optionally exclude incomplete training candidates.

    In sparse evaluation mode, a symbol must have complete training prices.
    Missing values in validation/test are preserved and never filled.
    """

    if not isinstance(prices, pd.DataFrame):
        raise TypeError("prices must be a pandas DataFrame")
    if prices.empty or len(prices) < 60:
        raise ValueError("At least 60 price observations are required")
    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("prices must have a DatetimeIndex")
    if prices.index.has_duplicates:
        raise ValueError("Duplicate dates are not allowed")
    if not prices.index.is_monotonic_increasing:
        raise ValueError("Price dates must be sorted ascending")
    if not prices.columns.is_unique:
        raise ValueError("Duplicate price columns are not allowed")
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("Train and validation fractions must total less than 1")

    try:
        numeric = prices.apply(pd.to_numeric, errors="raise")
    except (TypeError, ValueError) as exc:
        raise ValueError("Prices must contain numeric values or missing values") from exc

    values = numeric.to_numpy(dtype=float)
    observed_mask = ~np.isnan(values)
    observed_values = values[observed_mask]

    if not np.isfinite(observed_values).all():
        raise ValueError("Observed prices must be finite")
    if (observed_values <= 0).any():
        raise ValueError("Observed prices must be positive")

    total = len(numeric)
    train_end = int(total * train_fraction)
    validation_end = int(total * (train_fraction + validation_fraction))

    if train_end < 2 or validation_end - train_end < 2:
        raise ValueError("Each split needs enough observations")
    if total - validation_end < 2:
        raise ValueError("Test split needs at least two observations")

    original_columns = list(numeric.columns)
    training_window = numeric.iloc[:train_end]
    eligible_columns = [
        col for col in original_columns
        if training_window[col].notna().all()
    ]
    excluded_columns = [
        col for col in original_columns if col not in eligible_columns
    ]

    if excluded_columns and not allow_sparse_evaluation:
        raise ValueError("Missing prices are not allowed")
    if not eligible_columns:
        raise ValueError("No stocks have complete prices throughout training")

    selected = numeric.loc[:, eligible_columns]
    train = selected.iloc[:train_end].copy()
    validation = selected.iloc[train_end - 1:validation_end].copy()
    test = selected.iloc[validation_end - 1:].copy()

    if train.isna().any().any():
        raise ValueError("Training prices must be complete")
    if train.empty or validation.empty or test.empty:
        raise ValueError("Insufficient historical data for all periods")

    metadata = {
        "method": "CHRONOLOGICAL",
        "total_observations": total,
        "train_observations": len(train),
        "validation_observations": len(validation) - 1,
        "test_observations": len(test) - 1,
        "train_start": str(train.index[0].date()),
        "train_end": str(train.index[-1].date()),
        "validation_start": str(validation.index[1].date()),
        "validation_end": str(validation.index[-1].date()),
        "test_start": str(test.index[1].date()),
        "test_end": str(test.index[-1].date()),
        "candidate_columns_before_filter": len(original_columns),
        "eligible_training_symbols": eligible_columns,
        "excluded_incomplete_training_symbols": excluded_columns,
        "baseline_prices_included": True,
        "shuffled": False,
        "missing_prices_filled": False,
        "sparse_evaluation_allowed": allow_sparse_evaluation,
    }

    return DataSplits(train, validation, test, metadata)
