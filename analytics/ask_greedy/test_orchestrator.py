import pytest
from analytics.ask_greedy.orchestrator import _validate_plan, _extract_json
from analytics.ask_greedy.calculations import maximum_sharpe

def test_extract_json():
    assert _extract_json('```json\n{"operation":"none"}\n```')["operation"] == "none"

def test_reject_unknown_operation():
    with pytest.raises(ValueError):
        _validate_plan({"operation":"unknown","arguments":{}})

def test_reject_missing_arguments():
    with pytest.raises(ValueError):
        _validate_plan({"operation":"sharpe_ratio","arguments":{"volatility":0.2}})

def test_reject_extra_arguments():
    with pytest.raises(ValueError):
        _validate_plan({"operation":"drawdown","arguments":{"returns":[0.1],"extra":1}})

def test_q1_optimizer():
    c = [[1,.9,-.8],[.9,1,-.9],[-.8,-.9,1]]
    result = maximum_sharpe([.15,.12,.10],[.2,.15,.1],c,.05)
    assert result["sharpe_ratio"] == pytest.approx(2.162817, rel=1e-5)
    assert sum(result["weights"]) == pytest.approx(1)
