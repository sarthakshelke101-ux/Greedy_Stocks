from pathlib import Path
import sys, json, contextlib, io
import pandas as pd

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "analytics"))

from greedy_v2_data import prepare_greedy_v2_dataset
from greedy_v2_splits import chronological_split
from greedy_v2_engine import greedy_select_stocks

OUT = ROOT / "database" / "processed" / "analytics"
OUT.mkdir(parents=True, exist_ok=True)

def main():
    print("\nGREEDY V2 — TRAINING STABILITY ANALYSIS")
    print("=" * 72)

    dataset = prepare_greedy_v2_dataset(
        start_date="2025-04-01",
        end_date="2026-11-05",
    )

    splits = chronological_split(
        dataset.adjusted_prices,
        train_fraction=0.60,
        validation_fraction=0.20,
        allow_sparse_evaluation=True,
    )

    full_train = splits.train
    sectors = dataset.sectors

    windows = [90, 120, 180, len(full_train)]
    caps = [1, 2, 3, 5]
    rows = []
    selections = {}

    print("\nTraining observations available:", len(full_train))
    print("Eligible symbols:", len(full_train.columns))
    print("Training period:", full_train.index.min().date(),
          "to", full_train.index.max().date())

    for window in windows:
        train = full_train.tail(window)
        if len(train) < 60:
            continue

        for cap in caps:
            label = f"W{window}_CAP{cap}"

            try:
                with contextlib.redirect_stdout(io.StringIO()):
                    result = greedy_select_stocks(
                        train_prices=train,
                        sectors=sectors,
                        target_stocks=10,
                        max_per_sector=cap,
                        risk_free_rate=0.0,
                    )

                symbols = result["selected_symbols"]
                log = result["selection_log"]

                sector_counts = {}
                for symbol in symbols:
                    sector = sectors[symbol]
                    sector_counts[sector] = sector_counts.get(sector, 0) + 1

                selections[label] = symbols

                rows.append({
                    "configuration": label,
                    "training_observations": len(train),
                    "training_start": str(train.index.min().date()),
                    "training_end": str(train.index.max().date()),
                    "sector_cap": cap,
                    "selected_count": len(symbols),
                    "unique_sectors": len(sector_counts),
                    "maximum_sector_count": max(sector_counts.values()),
                    "selected_symbols": ",".join(symbols),
                    "final_training_sharpe": float(
                        result["portfolio_result"]["metrics"]["sharpe_ratio"]
                    ),
                    "selection_path_sharpes": ",".join(
                        f"{float(x):.5f}"
                        for x in log["portfolio_sharpe"]
                    ),
                    "status": "SUCCESS",
                })

                print(
                    f"{label:18} | "
                    f"{len(train):3} days | "
                    f"{len(sector_counts):2} sectors | "
                    f"max sector={max(sector_counts.values())} | "
                    f"Sharpe={rows[-1]['final_training_sharpe']:.4f}"
                )

            except Exception as exc:
                rows.append({
                    "configuration": label,
                    "training_observations": len(train),
                    "sector_cap": cap,
                    "status": "FAILED",
                    "error": str(exc),
                })
                print(label, "FAILED:", exc)

    results = pd.DataFrame(rows)
    results.to_csv(
        OUT / "greedy_training_stability.csv",
        index=False,
    )

    overlap_rows = []
    successful = {
        key: value for key, value in selections.items()
    }

    for name_a, symbols_a in successful.items():
        for name_b, symbols_b in successful.items():
            if name_a >= name_b:
                continue

            a, b = set(symbols_a), set(symbols_b)
            intersection = len(a & b)
            union = len(a | b)

            overlap_rows.append({
                "configuration_a": name_a,
                "configuration_b": name_b,
                "common_stocks": intersection,
                "jaccard_similarity": intersection / union if union else 0,
                "only_a": ",".join(sorted(a - b)),
                "only_b": ",".join(sorted(b - a)),
            })

    overlap = pd.DataFrame(overlap_rows)
    overlap.to_csv(
        OUT / "greedy_training_stability_overlap.csv",
        index=False,
    )

    report = {
        "analysis": "GREEDY_V2_TRAINING_WINDOW_AND_SECTOR_CAP_SENSITIVITY",
        "windows": windows,
        "sector_caps": caps,
        "target_stocks": 10,
        "training_only": True,
        "database_writes": False,
        "trial_registry_writes": False,
        "algorithm_modified": False,
        "results": rows,
        "overlap": overlap_rows,
        "interpretation_warning": (
            "This is a selection-stability diagnostic. "
            "Training Sharpe is not out-of-sample performance."
        ),
    }

    with (OUT / "greedy_training_stability.json").open(
        "w", encoding="utf-8"
    ) as f:
        json.dump(report, f, indent=2, allow_nan=False)

    print("\nCONFIGURATION RESULTS")
    print(results.to_string(index=False))

    if not overlap.empty:
        print("\nPAIRWISE SELECTION OVERLAP")
        print(overlap.sort_values(
            ["common_stocks", "jaccard_similarity"],
            ascending=[True, True],
        ).to_string(index=False))

    print("\nFILES SAVED:")
    print(OUT / "greedy_training_stability.csv")
    print(OUT / "greedy_training_stability_overlap.csv")
    print(OUT / "greedy_training_stability.json")
    print("\nSTABILITY ANALYSIS COMPLETE — NO ALGORITHM OR DB CHANGES.")

if __name__ == "__main__":
    main()
