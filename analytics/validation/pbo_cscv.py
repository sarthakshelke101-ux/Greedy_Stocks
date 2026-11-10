"""Combinatorially Symmetric Cross-Validation estimate of PBO."""

from itertools import combinations
import math

import numpy as np
import pandas as pd
from scipy.stats import rankdata


def _sharpe(values):
    values = np.asarray(values, dtype=float)
    if values.size < 2 or not np.isfinite(values).all():
        raise ValueError("Each partition needs >=2 finite returns")
    volatility = values.std(ddof=1)
    if volatility <= 0:
        return np.nan
    return float(values.mean() / volatility)


def estimate_pbo(returns, n_slices=6):
    """Estimate PBO from T x N aligned daily strategy returns.

    All combinations of n_slices/2 time blocks are evaluated.
    PBO is the fraction of splits where the IS winner ranks below
    the OOS median. Sharpe is calculated at the native return frequency.
    """
    if not isinstance(returns, pd.DataFrame):
        raise TypeError("returns must be a pandas DataFrame")
    if returns.shape[1] < 2:
        raise ValueError("At least two strategy columns are required")
    if not isinstance(n_slices, int) or n_slices < 2 or n_slices % 2:
        raise ValueError("n_slices must be an even integer >= 2")
    if returns.shape[0] < n_slices * 2:
        raise ValueError("Insufficient observations for requested slices")
    if returns.columns.has_duplicates:
        raise ValueError("Strategy column names must be unique")

    matrix = returns.to_numpy(dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError("Returns matrix must be complete and finite")

    blocks = np.array_split(np.arange(len(returns)), n_slices)
    if min(map(len, blocks)) < 2:
        raise ValueError("Each time block must contain at least two returns")

    split_results = []
    all_blocks = set(range(n_slices))
    half = n_slices // 2

    for chosen in combinations(range(n_slices), half):
        is_blocks = set(chosen)
        oos_blocks = sorted(all_blocks - is_blocks)

        is_rows = np.concatenate([blocks[i] for i in chosen])
        oos_rows = np.concatenate([blocks[i] for i in oos_blocks])

        is_scores = np.array([
            _sharpe(matrix[is_rows, col])
            for col in range(matrix.shape[1])
        ])
        oos_scores = np.array([
            _sharpe(matrix[oos_rows, col])
            for col in range(matrix.shape[1])
        ])

        if not np.isfinite(is_scores).all() or not np.isfinite(oos_scores).all():
            raise ValueError("A strategy has zero volatility in a CSCV partition")

        winner = int(np.argmax(is_scores))
        # Rank 1 is best; rank N is worst.
        oos_rank = float(rankdata(-oos_scores, method="average")[winner])
        omega = oos_rank / (matrix.shape[1] + 1.0)

        split_results.append({
            "in_sample_blocks": list(chosen),
            "selected_strategy": str(returns.columns[winner]),
            "oos_rank": oos_rank,
            "relative_oos_rank": omega,
            "overfit": bool(omega > 0.5),
        })

    pbo = sum(x["overfit"] for x in split_results) / len(split_results)

    return {
        "pbo": float(pbo),
        "splits": len(split_results),
        "n_strategies": int(returns.shape[1]),
        "observations": int(returns.shape[0]),
        "n_slices": n_slices,
        "split_results": split_results,
        "method": "CSCV; all half-and-half block combinations",
        "assumption": (
            "Comparable strategy returns on identical dates; "
            "CSCV is a diagnostic, not a live holdout"
        ),
    }
