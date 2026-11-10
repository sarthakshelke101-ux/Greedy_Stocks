"""Deterministic financial calculation engine for Ask GREEDY."""
from __future__ import annotations

import math
import numpy as np


def _finite_array(values, name):
    a = np.asarray(values, dtype=float)
    if not np.all(np.isfinite(a)):
        raise ValueError(f"{name} must contain only finite numbers.")
    return a


def portfolio_return(weights, returns):
    w = _finite_array(weights, "weights")
    r = _finite_array(returns, "returns")
    if w.ndim != 1 or r.ndim != 1 or len(w) != len(r):
        raise ValueError("Weights and returns must be equal-length vectors.")
    if np.any(w < 0) or not np.isclose(w.sum(), 1):
        raise ValueError("Weights must be non-negative and sum to 1.")
    return float(w @ r)


def sharpe_ratio(expected_return, risk_free_rate, volatility):
    if volatility <= 0 or not math.isfinite(volatility):
        raise ValueError("Volatility must be positive and finite.")
    return float((expected_return - risk_free_rate) / volatility)


def portfolio_volatility(weights, volatilities, correlations):
    w = _finite_array(weights, "weights")
    s = _finite_array(volatilities, "volatilities")
    c = _finite_array(correlations, "correlations")

    if c.shape != (len(w), len(w)) or len(s) != len(w):
        raise ValueError("Incompatible portfolio dimensions.")
    if np.any(w < 0) or not np.isclose(w.sum(), 1):
        raise ValueError("Weights must be non-negative and sum to 1.")
    if np.any(s < 0):
        raise ValueError("Volatilities cannot be negative.")
    if not np.allclose(c, c.T, atol=1e-10):
        raise ValueError("Correlation matrix must be symmetric.")
    if not np.allclose(np.diag(c), 1, atol=1e-10):
        raise ValueError("Correlation matrix diagonal must equal 1.")
    if np.any(np.abs(c) > 1 + 1e-10):
        raise ValueError("Correlations must lie between -1 and 1.")

    eigenvalues = np.linalg.eigvalsh(c)
    if eigenvalues.min() < -1e-9:
        raise ValueError(
            f"Invalid correlation matrix: minimum eigenvalue "
            f"{eigenvalues.min():.10f}"
        )

    cov = np.outer(s, s) * c
    variance = float(w @ cov @ w)
    if variance < -1e-10:
        raise ValueError("Calculated portfolio variance is negative.")
    return math.sqrt(max(0.0, variance))


def validate_correlation_matrix(correlations, tolerance=1e-9):
    c = _finite_array(correlations, "correlations")
    if c.ndim != 2 or c.shape[0] != c.shape[1]:
        return {"valid": False, "reason": "Matrix must be square."}
    symmetric = bool(np.allclose(c, c.T, atol=tolerance))
    diagonal = bool(np.allclose(np.diag(c), 1, atol=tolerance))
    bounded = bool(np.all(np.abs(c) <= 1 + tolerance))
    eigenvalues = np.linalg.eigvalsh((c + c.T) / 2)
    minimum = float(eigenvalues.min())
    valid = symmetric and diagonal and bounded and minimum >= -tolerance
    return {
        "valid": valid,
        "symmetric": symmetric,
        "unit_diagonal": diagonal,
        "bounded": bounded,
        "minimum_eigenvalue": minimum,
        "determinant": float(np.linalg.det(c)),
        "reason": "Positive semidefinite correlation matrix."
                  if valid else "One or more correlation constraints failed."
    }


def maximum_sharpe(returns, volatilities, correlations, risk_free_rate=0.0):
    """Long-only maximum-Sharpe portfolio; deterministic multistart SLSQP."""
    from scipy.optimize import minimize

    r = _finite_array(returns, "returns")
    s = _finite_array(volatilities, "volatilities")
    c = _finite_array(correlations, "correlations")
    n = len(r)

    if n < 1 or len(s) != n or c.shape != (n, n):
        raise ValueError("Incompatible input dimensions.")
    if np.any(s <= 0):
        raise ValueError("All volatilities must be positive.")
    matrix_check = validate_correlation_matrix(c)
    if not matrix_check["valid"]:
        raise ValueError(matrix_check["reason"])

    cov = np.outer(s, s) * c

    def objective(w):
        variance = float(w @ cov @ w)
        if variance <= 1e-16:
            return 1e9
        return -float((w @ r - risk_free_rate) / math.sqrt(variance))

    constraints = [{"type": "eq", "fun": lambda w: np.sum(w) - 1}]
    bounds = [(0.0, 1.0)] * n
    starts = [np.full(n, 1 / n)]
    starts += [np.eye(n)[i] for i in range(n)]

    candidates = []
    for start in starts:
        result = minimize(
            objective, start, method="SLSQP",
            bounds=bounds, constraints=constraints,
            options={"maxiter": 2000, "ftol": 1e-12}
        )
        if result.success and np.all(np.isfinite(result.x)):
            w = np.maximum(result.x, 0)
            w /= w.sum()
            candidates.append(w)

    if not candidates:
        raise RuntimeError("Optimisation failed to converge.")

    weights = min(candidates, key=objective)
    ret = float(weights @ r)
    vol = math.sqrt(float(weights @ cov @ weights))
    return {
        "weights": weights.tolist(),
        "expected_return": ret,
        "volatility": vol,
        "sharpe_ratio": sharpe_ratio(ret, risk_free_rate, vol),
        "optimizer": "SLSQP deterministic multistart",
        "matrix_validation": matrix_check
    }


def drawdown(returns):
    r = _finite_array(returns, "returns")
    if np.any(r < -1):
        raise ValueError("A return cannot be below -100%.")
    wealth = np.cumprod(1 + r)
    peaks = np.maximum.accumulate(np.r_[1.0, wealth])[1:]
    dd = wealth / peaks - 1
    return float(dd.min())


def whole_share_allocation(capital, prices):
    if not math.isfinite(capital) or capital < 0:
        raise ValueError("Capital must be non-negative.")
    p = _finite_array(prices, "prices")
    if np.any(p <= 0):
        raise ValueError("Prices must be positive.")
    quantities = np.zeros(len(p), dtype=int)
    remaining = float(capital)

    # One share each, if affordable, then distribute remaining
    # capital by iterative affordable-share allocation.
    for i in np.argsort(p):
        if p[i] <= remaining:
            quantities[i] += 1
            remaining -= p[i]

    while True:
        affordable = np.where(p <= remaining + 1e-9)[0]
        if len(affordable) == 0:
            break
        i = int(affordable[np.argmin(p[affordable])])
        quantities[i] += 1
        remaining -= p[i]

    return {
        "quantities": quantities.tolist(),
        "invested": float(quantities @ p),
        "cash_remaining": float(remaining),
        "all_stocks_held": bool(np.all(quantities > 0))
    }
