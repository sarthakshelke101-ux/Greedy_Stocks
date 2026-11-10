"""Validated bridge between Gemini and deterministic calculations."""
import json
import logging
import re
import math

from .calculations import (
    portfolio_return, sharpe_ratio, portfolio_volatility,
    validate_correlation_matrix, maximum_sharpe,
    drawdown, whole_share_allocation,
)

logger = logging.getLogger("greedy_stocks_chat.calculations")

OPERATIONS = {
    "portfolio_return": portfolio_return,
    "sharpe_ratio": sharpe_ratio,
    "portfolio_volatility": portfolio_volatility,
    "validate_correlation_matrix": validate_correlation_matrix,
    "maximum_sharpe": maximum_sharpe,
    "drawdown": drawdown,
    "whole_share_allocation": whole_share_allocation,
}

CALCULATION_HINTS = re.compile(
    r"\b(calculate|compute|optimis|optimiz|maximi[sz]e|sharpe|"
    r"volatility|drawdown|portfolio return|weighted return|"
    r"correlation matrix|allocate|allocation|weights?)\b",
    re.IGNORECASE,
)

PLANNER_INSTRUCTION = """
Extract calculation inputs from the user's question.
Return exactly one JSON object, no markdown.

Supported schemas:
portfolio_return: {"weights":[...],"returns":[...]}
sharpe_ratio: {"expected_return":number,"risk_free_rate":number,"volatility":number}
portfolio_volatility: {"weights":[...],"volatilities":[...],"correlations":[[...]]}
validate_correlation_matrix: {"correlations":[[...]]}
maximum_sharpe: {"returns":[...],"volatilities":[...],"correlations":[[...]],"risk_free_rate":number}
drawdown: {"returns":[...]}
whole_share_allocation: {"capital":number,"prices":[...]}

Return format:
{"operation":"operation_name","arguments":{...}}
or
{"operation":"none","reason":"missing or ambiguous inputs"}

Rules:
- Extract only numbers explicitly supplied by the user.
- Never invent inputs or market data.
- Convert percentages to decimal fractions: 15% = 0.15.
- For unsupported, incomplete or ambiguous requests, return operation none.
- Preserve asset order.
- Do not perform the calculation or answer the question.
"""

ALLOWED = {
    "portfolio_return": {"weights", "returns"},
    "sharpe_ratio": {"expected_return", "risk_free_rate", "volatility"},
    "portfolio_volatility": {"weights", "volatilities", "correlations"},
    "validate_correlation_matrix": {"correlations"},
    "maximum_sharpe": {"returns", "volatilities", "correlations", "risk_free_rate"},
    "drawdown": {"returns"},
    "whole_share_allocation": {"capital", "prices"},
}

def _extract_json(text):
    text = (text or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
    text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Planner returned no JSON object.")
    return json.loads(text[start:end + 1])

def _validate_plan(plan):
    if not isinstance(plan, dict):
        raise ValueError("Invalid plan.")
    operation = plan.get("operation")
    if operation == "none":
        return None
    if operation not in OPERATIONS:
        raise ValueError("Unsupported operation.")
    args = plan.get("arguments")
    if not isinstance(args, dict) or set(args) != ALLOWED[operation]:
        raise ValueError("Arguments do not match the operation schema.")

    def check(value, depth=0):
        if depth > 3:
            raise ValueError("Input nesting is too deep.")
        if isinstance(value, list):
            if len(value) > 50:
                raise ValueError("Input array is too large.")
            for item in value:
                check(item, depth + 1)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                raise ValueError("Inputs must be finite.")
        else:
            raise ValueError("Inputs must contain numeric values only.")

    for value in args.values():
        check(value)
    return operation, args

def build_calculation_context(client, model, question):
    if not CALCULATION_HINTS.search(question or ""):
        return "No deterministic calculation was requested."

    try:
        interaction = client.interactions.create(
            model=model,
            input=PLANNER_INSTRUCTION + "\n\nUSER QUESTION:\n" + question,
            system_instruction=(
                "Extract explicit numeric inputs only. Never invent values. "
                "Return one JSON object only."
            ),
        )
        plan = _extract_json(interaction.output_text)
        validated = _validate_plan(plan)

        if validated is None:
            return (
                "NO_CALCULATION: "
                + str(plan.get("reason", "Required inputs were not explicit."))
            )

        operation, arguments = validated
        result = OPERATIONS[operation](**arguments)

        return json.dumps({
            "status": "CALCULATED",
            "operation": operation,
            "inputs": arguments,
            "result": result,
            "verification": "Executed by the deterministic Python calculation engine.",
        }, ensure_ascii=False, default=float)

    except Exception as exc:
        logger.warning("Calculation bridge did not execute: %s", exc)
        return (
            "NO_CALCULATION: The inputs could not be safely extracted or validated. "
            "Do not invent a result; ask the user to clarify."
        )
