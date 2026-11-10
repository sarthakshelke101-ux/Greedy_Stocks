from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path

log = logging.getLogger("greedy_v2_evidence")
ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "database" / "processed" / "analytics"

FILES = {
    "experiment": "greedy_v2_experiment.json",
    "baseline": "greedy_v2_baseline_comparison.json",
    "selection": "greedy_v2_selection_log.csv",
    "walk_results": "greedy_walk_forward_results.csv",
    "walk_selections": "walk_forward_selections.csv",
    "walk_report": "walk_forward_clean_report.json",
    "oos_summary": "greedy_out_of_sample_summary.csv",
}

STOPWORDS = {
    "ANALYSE", "ANALYSIS", "SHOW", "GIVE", "WHAT", "WHICH",
    "ABOUT", "STOCK", "SHARES", "GREEDY", "NIFTY", "INDIA",
    "SHARPE", "RATIO", "RETURN", "RETURNS", "VOLATILITY",
    "DRAWDOWN", "SELECTED", "SELECTION", "PORTFOLIO",
    "HISTORICAL", "PERFORMANCE", "EXPLAIN", "WHY", "WAS",
    "THE", "FOR", "AND", "WITH", "FROM", "LAST", "YEAR",
    "YEARS", "MONTH", "MONTHS", "1Y", "3M", "6M", "10Y",
}


def _read_json(name):
    path = ARTIFACTS / name
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _read_csv(name):
    path = ARTIFACTS / name
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _symbol_tokens(value):
    if value is None:
        return set()
    text = str(value).upper()
    return set(re.findall(r"(?<![A-Z0-9])[A-Z][A-Z0-9&._-]{1,19}(?![A-Z0-9])", text))


def _contains_symbol(row, symbol):
    for value in row.values():
        if symbol in _symbol_tokens(value):
            return True
    return False


def _question_symbol(question, known_symbols):
    tokens = _symbol_tokens(question)
    matches = sorted(tokens.intersection(known_symbols))
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        return None
    candidates = [
        token for token in tokens
        if token not in STOPWORDS and not token.isdigit()
    ]
    return candidates[0] if len(candidates) == 1 else None


def _compact_rows(rows, limit=12):
    return rows[:limit]


def build_greedy_v2_evidence_context(question):
    """Read-only evidence from saved Greedy V2 experiment artifacts."""
    try:
        experiment = _read_json(FILES["experiment"])
        baseline = _read_json(FILES["baseline"])
        walk_report = _read_json(FILES["walk_report"])
        selection_rows = _read_csv(FILES["selection"])
        walk_rows = _read_csv(FILES["walk_selections"])
        walk_results = _read_csv(FILES["walk_results"])
        oos_rows = _read_csv(FILES["oos_summary"])

        known = set()
        for row in selection_rows:
            for key in ("symbol", "selected_symbol"):
                known.update(_symbol_tokens(row.get(key)))
        if isinstance(experiment, dict):
            known.update(_symbol_tokens(experiment.get("selected_symbols", [])))
        for row in walk_rows:
            for key in ("symbol", "selected_symbol", "selected_stocks", "selected_symbols"):
                known.update(_symbol_tokens(row.get(key)))

        symbol = _question_symbol(question or "", known)

        selected_rows = [
            row for row in selection_rows
            if symbol and _contains_symbol(row, symbol)
        ]

        def row_symbols(row):
            raw = row.get("symbols", "")
            return {
                item.strip().upper()
                for item in str(raw).split(",")
                if item.strip()
            }

        # Only GREEDY_V2 rows count as Greedy V2 walk-forward selections.
        fold_rows = [
            row for row in walk_rows
            if symbol
            and str(row.get("strategy", "")).strip().upper() == "GREEDY_V2"
            and symbol in row_symbols(row)
        ]

        comparison_rows = [
            row for row in walk_rows
            if symbol
            and str(row.get("strategy", "")).strip().upper() != "GREEDY_V2"
            and symbol in row_symbols(row)
        ]

        metric_by_fold = {}
        for row in walk_results:
            if str(row.get("strategy", "GREEDY_V2")).strip().upper() == "GREEDY_V2":
                metric_by_fold[str(row.get("fold", ""))] = row

        matching_fold_metrics = [
            metric_by_fold[str(row.get("fold", ""))]
            for row in fold_rows
            if str(row.get("fold", "")) in metric_by_fold
        ]


        experiment_symbols = []
        if isinstance(experiment, dict):
            values = experiment.get("selected_symbols", [])
            if isinstance(values, list):
                experiment_symbols = [str(x) for x in values]

        in_main_experiment = bool(
            symbol and any(str(x).upper() == symbol for x in experiment_symbols)
        )

        result = {
            "status": "SAVED_ARTIFACTS_READ",
            "evidence_scope": "Historical saved experiment records; not a live rerun.",
            "requested_symbol": symbol,
            "experiment": experiment,
            "greedy_v2_selection_evidence": {
                "symbol_found_in_experiment_selected_symbols": in_main_experiment,
                "matching_winner_log_rows": selected_rows[:15],
                "interpretation": (
                    "A matching row records a stock selected as the winning addition at that step."
                    if selected_rows else
                    "No matching winner row was found. The selection log records winners, "
                    "not every candidate tested; absence does not prove the stock was rejected."
                ),
            },
            "walk_forward_evidence": {
                "matching_selection_rows": fold_rows[:30],
                "matching_fold_count": len(fold_rows),
                "matching_fold_metrics": matching_fold_metrics[:30],
                "other_strategy_comparison_rows": comparison_rows[:30],
            },
            "walk_forward_audit": walk_report,
            "out_of_sample_summary": oos_rows[:20],
            "random_baseline_comparison": baseline,
            "artifact_availability": {
                key: (ARTIFACTS / filename).exists()
                for key, filename in FILES.items()
            },
            "interpretation_limits": [
                "Saved selection logs show selected winners, not all rejected candidate scores.",
                "Walk-forward records describe saved historical folds, not future performance.",
                "Latest-constituent universe can introduce survivorship bias.",
                "Training selection Sharpe is not out-of-sample performance.",
                "Do not claim a stock was rejected unless a saved artifact explicitly proves it.",
                "Do not claim the algorithm was rerun; this connector only reads saved artifacts.",
            ],
        }

        if symbol is None:
            result["symbol_note"] = (
                "No unambiguous ticker was identified in the question. "
                "Ask the user for the NSE ticker if stock-specific evidence is required."
            )

        return (
            "GREEDY_V2_EVIDENCE_STATUS: SAVED_ARTIFACTS_READ\n"
            + json.dumps(result, indent=2, default=str)
        )

    except Exception as exc:
        log.exception("Greedy V2 evidence lookup failed")
        return (
            "GREEDY_V2_EVIDENCE_STATUS: UNAVAILABLE\n"
            f"Reason: {type(exc).__name__}: {str(exc)[:400]}\n"
            "Do not invent experiment results or selection evidence."
        )
