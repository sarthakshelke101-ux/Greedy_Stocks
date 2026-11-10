import json

import numpy as np
import pandas as pd
import pytest

from analytics.validation.trial_registry import append_trial, read_trials
from analytics.validation.deflated_sharpe import (
    expected_max_sharpe,
    deflated_sharpe,
)
from analytics.validation.pbo_cscv import estimate_pbo


def test_registry_appends_and_rejects_duplicate(tmp_path):
    path = tmp_path / "trials.jsonl"
    first = append_trial(
        "GREEDY_V2",
        {"target_stocks": 5},
        [0.01, -0.005, 0.02],
        dates=["2026-01-01", "2026-01-02", "2026-01-03"],
        trial_id="trial-001",
        path=path,
    )
    assert first["observations"] == 3
    assert len(read_trials(path)) == 1

    with pytest.raises(ValueError, match="Duplicate"):
        append_trial(
            "GREEDY_V2", {}, [0.01, 0.02],
            trial_id="trial-001", path=path
        )


def test_registry_rejects_nonfinite_returns(tmp_path):
    with pytest.raises(ValueError):
        append_trial("X", {}, [0.01, float("nan")], path=tmp_path / "x.jsonl")


def test_registry_dates_must_match_returns(tmp_path):
    with pytest.raises(ValueError):
        append_trial(
            "X", {}, [0.01, 0.02], dates=["2026-01-01"],
            path=tmp_path / "x.jsonl"
        )


def test_expected_max_sharpe_increases_with_trial_count():
    assert expected_max_sharpe(100) > expected_max_sharpe(10)


def test_dsr_is_probability_between_zero_and_one():
    result = deflated_sharpe(
        observed_sharpe=0.08,
        n_observations=500,
        n_trials=20,
        skewness=0.0,
        kurtosis=3.0,
        sharpe_std=0.05,
    )
    assert 0.0 <= result["dsr"] <= 1.0
    assert result["n_trials"] == 20


def test_dsr_rejects_invalid_observation_count():
    with pytest.raises(ValueError):
        deflated_sharpe(0.1, 2, 10, 0, 3)


def test_pbo_returns_valid_probability():
    rng = np.random.default_rng(42)
    data = rng.normal(0.0005, 0.01, size=(120, 5))
    frame = pd.DataFrame(data, columns=list("ABCDE"))
    result = estimate_pbo(frame, n_slices=6)
    assert 0.0 <= result["pbo"] <= 1.0
    assert result["splits"] == 20


def test_pbo_rejects_missing_returns():
    frame = pd.DataFrame({
        "A": [0.01, 0.02, np.nan, 0.01, 0.02, 0.01, 0.02, 0.01],
        "B": [0.02, 0.01, 0.01, 0.02, 0.01, 0.02, 0.01, 0.02],
    })
    with pytest.raises(ValueError, match="complete"):
        estimate_pbo(frame, n_slices=2)
