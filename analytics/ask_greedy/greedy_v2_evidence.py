from __future__ import annotations

import csv
import json
import logging
import re
from pathlib import Path

from analytics.validation.trial_registry import read_trials

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
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8-sig") as f:
        return json.load(f)


def _read_csv(name):
    path = ARTIFACTS / name
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _symbol_tokens(value):
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        value = " ".join(map(str, value))
    return set(re.findall(
        r"(?<![A-Z0-9])[A-Z][A-Z0-9&._-]{1,19}(?![A-Z0-9])",
        str(value).upper(),
    ))


def _contains_symbol(row, symbol):
    return any(symbol in _symbol_tokens(value) for value in row.values())


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


def _registry_evidence(experiment):
    """Resolve and verify the exact append-only registry record for this artifact."""
    execution = (experiment or {}).get("execution_metadata") or {}
    trial_id = execution.get("trial_id")
    fingerprint = execution.get("experiment_fingerprint")

    if not trial_id:
        return {
            "status": "UNLINKED",
            "reason": (
                "Experiment JSON has no execution_metadata.trial_id. "
                "The registry record cannot be safely associated with this artifact."
            ),
            "trial_id": None,
            "record": None,
        }

    records = read_trials()
    matches = [
        record for record in records
        if record.get("trial_id") == trial_id
        and str(record.get("algorithm", "")).upper() == "GREEDY_V2"
    ]
    if len(matches) != 1:
        return {
            "status": "MISSING_OR_DUPLICATE",
            "reason": f"Expected exactly one GREEDY_V2 registry record for {trial_id}; found {len(matches)}.",
            "trial_id": trial_id,
            "record": None,
        }

    record = matches[0]
    registry_fingerprint = (record.get("metadata") or {}).get(
        "experiment_fingerprint"
    )
    if fingerprint and registry_fingerprint != fingerprint:
        return {
            "status": "FINGERPRINT_MISMATCH",
            "reason": "The registry record fingerprint does not match the experiment JSON.",
            "trial_id": trial_id,
            "record": None,
        }

    report_symbols = (experiment or {}).get("selected_symbols") or []
    registry_symbols = (record.get("config") or {}).get("selected_symbols") or []
    if sorted(map(str.upper, report_symbols)) != sorted(map(str.upper, registry_symbols)):
        return {
            "status": "CONFIG_MISMATCH",
            "reason": "Selected symbols in JSON and registry config do not match.",
            "trial_id": trial_id,
            "record": None,
        }

    expected_observations = int(
        ((experiment or {}).get("period_results") or {})
        .get("final_test", {})
        .get("return_observations", 0)
    )
    if expected_observations and int(record.get("observations", -1)) != expected_observations:
        return {
            "status": "OBSERVATION_COUNT_MISMATCH",
            "reason": "Registry observations do not match final-test return observations.",
            "trial_id": trial_id,
            "record": None,
        }

    return {
        "status": "VERIFIED_MATCH",
        "reason": "Trial ID, algorithm, fingerprint, selected symbols and final-test observation count match.",
        "trial_id": trial_id,
        "record": record,
    }


def build_greedy_v2_evidence_context(question):
    """Read-only, execution-linked evidence from saved Greedy V2 artifacts."""
    try:
        experiment = _read_json(FILES["experiment"])
        baseline = _read_json(FILES["baseline"])
        walk_report = _read_json(FILES["walk_report"])
        selection_rows = _read_csv(FILES["selection"])
        walk_rows = _read_csv(FILES["walk_selections"])
        walk_results = _read_csv(FILES["walk_results"])
        oos_rows = _read_csv(FILES["oos_summary"])

        if not isinstance(experiment, dict):
            return (
                "GREEDY_V2_EVIDENCE_STATUS: UNAVAILABLE\n"
                "Reason: The experiment JSON is missing or is not a JSON object.\n"
                "Do not invent experiment results."
            )

        registry = _registry_evidence(experiment)
        execution = experiment.get("execution_metadata") or {}
        trial_id = execution.get("trial_id")
        fingerprint = execution.get("experiment_fingerprint")

        # Refuse to present a selection CSV as belonging to this execution
        # unless its execution identity matches the JSON.
        csv_trial_ids = {
            str(row.get("trial_id", "")).strip()
            for row in selection_rows if row.get("trial_id")
        }
        csv_fingerprints = {
            str(row.get("experiment_fingerprint", "")).strip()
            for row in selection_rows if row.get("experiment_fingerprint")
        }
        csv_identity = {
            "status": "VERIFIED_MATCH",
            "row_count": len(selection_rows),
        }
        if selection_rows:
            if not trial_id or csv_trial_ids != {str(trial_id)}:
                csv_identity = {
                    "status": "MISMATCH_OR_UNTAGGED",
                    "row_count": len(selection_rows),
                    "observed_trial_ids": sorted(csv_trial_ids),
                    "expected_trial_id": trial_id,
                }
                selection_rows = []
            elif fingerprint and csv_fingerprints != {str(fingerprint)}:
                csv_identity = {
                    "status": "FINGERPRINT_MISMATCH",
                    "row_count": len(selection_rows),
                }
                selection_rows = []
        else:
            csv_identity = {
                "status": "MISSING_OR_EMPTY",
                "row_count": 0,
            }

        known = set()
        for row in selection_rows:
            for key in ("symbol", "selected_symbol"):
                known.update(_symbol_tokens(row.get(key)))
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
            return {item.strip().upper() for item in str(raw).split(",") if item.strip()}

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

        experiment_symbols = [
            str(x) for x in experiment.get("selected_symbols", [])
        ]
        in_main_experiment = bool(
            symbol and any(x.upper() == symbol for x in experiment_symbols)
        )

        result = {
            "status": "SAVED_ARTIFACTS_READ",
            "evidence_scope": "Saved historical records; no strategy rerun performed.",
            "execution_metadata": execution,
            "registry_verification": registry,
            "selection_csv_identity": csv_identity,
            "requested_symbol": symbol,
            "experiment": experiment,
            "greedy_v2_selection_evidence": {
                "symbol_found_in_experiment_selected_symbols": in_main_experiment,
                "matching_winner_log_rows": selected_rows[:30],
                "interpretation": (
                    "A matching row records a stock selected as the winning addition at that step."
                    if selected_rows else
                    "No matching winner row was found. The selection log records winners, "
                    "not every candidate tested; absence does not prove rejection."
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
                key: (ARTIFACTS / filename).is_file()
                for key, filename in FILES.items()
            },
            "interpretation_limits": [
                "JSON, CSV and registry are separate artifacts; identity checks are required before treating them as one execution.",
                "A matching registry record verifies the registered final-test return series, not every JSON metric.",
                "Selection logs show selected winners, not every rejected candidate score.",
                "Walk-forward records are separate saved evidence and are not automatically part of this trial.",
                "Latest-constituent universe can introduce survivorship bias.",
                "Training selection Sharpe is not out-of-sample performance.",
                "Do not claim a stock was rejected unless a saved artifact explicitly proves it.",
                "Do not claim the algorithm was rerun; this module only reads saved artifacts.",
            ],
        }

        if symbol is None:
            result["symbol_note"] = (
                "No unambiguous ticker was identified. Ask for the NSE ticker only "
                "when stock-specific selection evidence is needed."
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
