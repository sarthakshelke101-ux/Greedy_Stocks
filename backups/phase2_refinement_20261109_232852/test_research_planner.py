
import pytest

from analytics.ask_greedy.research_planner import (
    _extract_json,
    validate_research_plan,
    fallback_research_plan,
    execute_research_plan,
    format_execution_context,
)


def market():
    return {
        "id": "market",
        "operation": "market_research",
        "query": "Research NIFTY 50",
        "depends_on": [],
    }


def test_extract_planner_json():
    assert _extract_json(
        '```json\n{"operations":[]}\n```'
    ) == {"operations": []}


def test_valid_multi_operation_plan():
    plan = {
        "operations": [
            market(),
            {
                "id": "calc",
                "operation": "calculation",
                "query": "Calculate the portfolio return",
                "depends_on": ["market"],
            },
            {
                "id": "history",
                "operation": "historical_analysis",
                "query": "Analyse RELIANCE",
                "depends_on": [],
            },
        ]
    }
    assert len(validate_research_plan(plan)) == 3


def test_reject_unknown_operation():
    plan = {"operations": [
        {**market(), "operation": "execute_sql"}
    ]}
    with pytest.raises(ValueError):
        validate_research_plan(plan)


def test_reject_missing_market_operation():
    plan = {"operations": [{
        "id": "calc",
        "operation": "calculation",
        "query": "Calculate",
        "depends_on": [],
    }]}
    with pytest.raises(ValueError):
        validate_research_plan(plan)


def test_reject_duplicate_ids():
    first = market()
    second = {
        "id": "market",
        "operation": "calculation",
        "query": "Calculate",
        "depends_on": [],
    }
    with pytest.raises(ValueError):
        validate_research_plan({"operations": [first, second]})


def test_reject_forward_dependency():
    first = market()
    first["depends_on"] = ["later"]
    with pytest.raises(ValueError):
        validate_research_plan({"operations": [first]})


def test_reject_extra_fields():
    first = market()
    first["python_code"] = "print(1)"
    with pytest.raises(ValueError):
        validate_research_plan({"operations": [first]})


def test_reject_empty_query():
    first = market()
    first["query"] = " "
    with pytest.raises(ValueError):
        validate_research_plan({"operations": [first]})


def test_fallback_plans_multiple_research_operations():
    plan = fallback_research_plan(
        "Analyse RELIANCE historical returns and calculate Sharpe ratio"
    )
    names = {item["operation"] for item in plan}
    assert "market_research" in names
    assert "historical_analysis" in names
    assert "calculation" in names


def test_executor_runs_in_plan_order():
    plan = validate_research_plan({"operations": [
        market(),
        {
            "id": "calc",
            "operation": "calculation",
            "query": "Calculate",
            "depends_on": ["market"],
        },
    ]})

    calls = []
    handlers = {
        "market_research": lambda q: calls.append("market") or "data",
        "calculation": lambda q: calls.append("calculation") or "result",
    }

    results = execute_research_plan(plan, handlers)

    assert calls == ["market", "calculation"]
    assert all(item["status"] == "COMPLETED" for item in results)


def test_failed_dependency_skips_dependent_operation():
    plan = validate_research_plan({"operations": [
        market(),
        {
            "id": "calc",
            "operation": "calculation",
            "query": "Calculate",
            "depends_on": ["market"],
        },
    ]})

    results = execute_research_plan(
        plan,
        {
            "market_research": lambda q: (_ for _ in ()).throw(
                RuntimeError("Unavailable")
            ),
            "calculation": lambda q: "must not execute",
        },
    )

    assert results[0]["status"] == "FAILED"
    assert results[1]["status"] == "SKIPPED"


def test_independent_operation_runs_after_failure():
    plan = validate_research_plan({"operations": [
        market(),
        {
            "id": "history",
            "operation": "historical_analysis",
            "query": "Analyse stock",
            "depends_on": [],
        },
    ]})

    results = execute_research_plan(
        plan,
        {
            "market_research": lambda q: (_ for _ in ()).throw(
                RuntimeError("Unavailable")
            ),
            "historical_analysis": lambda q: "historical data",
        },
    )

    assert results[1]["status"] == "COMPLETED"


def test_missing_handler_is_reported():
    plan = validate_research_plan({"operations": [market()]})
    result = execute_research_plan(plan, {})
    assert result[0]["status"] == "FAILED"


def test_execution_context_discloses_plan():
    plan = validate_research_plan({"operations": [market()]})
    results = execute_research_plan(
        plan,
        {"market_research": lambda q: "verified context"},
    )
    context = format_execution_context(
        plan, "TEST", results
    )
    assert "COMPLETED" in context
    assert "market_research" in context
    assert "verified context" in context
