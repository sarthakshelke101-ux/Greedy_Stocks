from pathlib import Path
import pandas as pd
import numpy as np
import json

ROOT = Path.cwd()
OUT = ROOT / "database" / "processed" / "analytics"

fold_path = OUT / "walk_forward_fold_metrics.csv"
daily_path = OUT / "walk_forward_daily_returns.csv"
selection_path = OUT / "walk_forward_selections.csv"

folds = pd.read_csv(fold_path)
daily = pd.read_csv(daily_path)
selections = pd.read_csv(selection_path)

print("\nWALK-FORWARD RESULTS — METHODOLOGY AUDIT")
print("=" * 72)

# 1. Identify complete folds.
fold_lengths = (
    daily.groupby(["fold", "mode", "strategy", "cost_bps"])
    .size()
    .reset_index(name="observations")
)

print("\n[1] FOLD LENGTHS")
print(fold_lengths.to_string(index=False))

# All primary folds must have the intended 30 observations.
complete_ids = sorted(
    fold_lengths.loc[
        fold_lengths["observations"] == 30, "fold"
    ].unique()
)

incomplete_ids = sorted(
    set(fold_lengths["fold"].unique()) - set(complete_ids)
)

print("\nComplete folds:", complete_ids)
print("Incomplete folds excluded:", incomplete_ids)

if len(complete_ids) < 2:
    raise RuntimeError("Insufficient complete folds for comparison.")

# 2. Keep only full folds.
clean = daily[daily["fold"].isin(complete_ids)].copy()
clean["date"] = pd.to_datetime(clean["date"])

# 3. Continuous OOS paths by mode/strategy/cost.
paths = []
summary = []

for (mode, strategy, cost), group in clean.groupby(
    ["mode", "strategy", "cost_bps"]
):
    group = group.sort_values(["fold", "date"])

    if group["date"].duplicated().any():
        raise ValueError("Duplicate OOS dates detected.")

    returns = group["net_return"].to_numpy(dtype=float)

    if not np.isfinite(returns).all():
        raise ValueError("Non-finite OOS returns.")

    equity = np.cumprod(1 + returns)
    peaks = np.maximum.accumulate(equity)
    drawdown = equity / peaks - 1

    vol = np.std(returns, ddof=1)
    sharpe = (
        np.mean(returns) / vol * np.sqrt(252)
        if vol > 0 else None
    )

    summary.append({
        "mode": mode,
        "strategy": strategy,
        "cost_bps": int(cost),
        "complete_folds": len(complete_ids),
        "observations": len(returns),
        "continuous_oos_return_pct": float((equity[-1] - 1) * 100),
        "annualized_sharpe": (
            float(sharpe) if sharpe is not None else None
        ),
        "maximum_drawdown_pct": float(drawdown.min() * 100),
        "mean_daily_return_pct": float(np.mean(returns) * 100),
    })

    for date, value, eq in zip(
        group["date"], returns, equity
    ):
        paths.append({
            "date": str(date.date()),
            "mode": mode,
            "strategy": strategy,
            "cost_bps": int(cost),
            "daily_return": float(value),
            "equity": float(eq),
        })

summary_df = pd.DataFrame(summary)
paths_df = pd.DataFrame(paths)

# 4. Separate valid primary comparisons from hindsight baseline.
summary_df["comparison_status"] = np.where(
    summary_df["strategy"] == "TOP10_INDEX_WEIGHT_SELECTED",
    "HINDSIGHT_BASELINE_NOT_VALID_FOR_HISTORICAL_CLAIMS",
    "SURVIVORSHIP_BIASED_EXPLORATORY_COMPARISON",
)

# 5. Save outputs.
summary_df.to_csv(
    OUT / "walk_forward_clean_summary.csv",
    index=False,
)
paths_df.to_csv(
    OUT / "walk_forward_clean_oos_paths.csv",
    index=False,
)

report = {
    "experiment": "CLEANED_WALK_FORWARD_AUDIT",
    "complete_folds": complete_ids,
    "incomplete_folds_excluded": incomplete_ids,
    "primary_comparison": [
        "GREEDY_V2",
        "EQUAL_WEIGHT_UNIVERSE",
    ],
    "hindsight_baseline": (
        "TOP10_INDEX_WEIGHT_SELECTED uses latest constituent weights; "
        "excluded from valid historical superiority claims."
    ),
    "universe_warning": (
        "Latest eligible universe creates survivorship bias."
    ),
    "aggregation": (
        "Continuous compounding over non-overlapping complete OOS folds."
    ),
    "limitations": [
        "Historical sample is already observed.",
        "Latest constituent universe creates survivorship bias.",
        "Latest index weights create look-ahead bias in TOP10 baseline.",
        "Transaction costs are simplified basis-point estimates.",
        "Dividends excluded.",
        "Corporate-action coverage partial.",
    ],
    "summary": summary,
}

with (OUT / "walk_forward_clean_report.json").open(
    "w", encoding="utf-8"
) as f:
    json.dump(
        report,
        f,
        indent=2,
        allow_nan=False,
        default=lambda value: value.item()
        if hasattr(value, "item") else str(value)
    )

print("\n[2] CLEAN CONTINUOUS OOS RESULTS")
print(summary_df.to_string(index=False))

print("\n[3] FILES")
print(OUT / "walk_forward_clean_summary.csv")
print(OUT / "walk_forward_clean_oos_paths.csv")
print(OUT / "walk_forward_clean_report.json")

print("\nCLEANED AUDIT COMPLETE — ORIGINAL RESULTS PRESERVED.")
