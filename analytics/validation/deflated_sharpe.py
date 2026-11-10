"""Deflated Sharpe Ratio utilities.

Sharpe inputs are per-observation-period, not annualised.
Kurtosis is Pearson kurtosis (normal distribution = 3).
The expected-maximum approximation assumes independent trials.
"""

import math
from scipy.stats import norm


EULER_GAMMA = 0.5772156649015329


def expected_max_sharpe(n_trials, sharpe_std=1.0):
    """Approximate expected maximum under a zero-mean Gaussian null."""
    if not isinstance(n_trials, int) or n_trials < 2:
        raise ValueError("n_trials must be an integer >= 2")
    if not math.isfinite(sharpe_std) or sharpe_std <= 0:
        raise ValueError("sharpe_std must be finite and > 0")

    log_n = math.log(n_trials)
    root = math.sqrt(2.0 * log_n)
    unit_expected_max = (
        root * (1.0 - EULER_GAMMA / (2.0 * log_n))
        + EULER_GAMMA / root
    )
    return sharpe_std * unit_expected_max


def deflated_sharpe(
    observed_sharpe,
    n_observations,
    n_trials,
    skewness,
    kurtosis,
    sharpe_std=1.0,
):
    """Return DSR probability and its intermediate quantities.

    Use daily (or other consistent period) Sharpe, not annualised Sharpe.
    This is the PSR formula with the expected maximum Sharpe as benchmark.
    """
    values = (
        observed_sharpe, skewness, kurtosis, sharpe_std
    )
    if not all(math.isfinite(float(x)) for x in values):
        raise ValueError("All numeric inputs must be finite")
    if not isinstance(n_observations, int) or n_observations < 3:
        raise ValueError("n_observations must be an integer >= 3")
    if kurtosis <= 0:
        raise ValueError("kurtosis must be Pearson kurtosis > 0")

    benchmark = expected_max_sharpe(n_trials, sharpe_std)
    variance_term = (
        1.0
        - skewness * observed_sharpe
        + ((kurtosis - 1.0) / 4.0) * observed_sharpe ** 2
    )
    if not math.isfinite(variance_term) or variance_term <= 0:
        raise ValueError("Invalid/non-positive PSR variance term")

    z_score = (
        (observed_sharpe - benchmark)
        * math.sqrt(n_observations - 1)
        / math.sqrt(variance_term)
    )

    return {
        "dsr": float(norm.cdf(z_score)),
        "z_score": float(z_score),
        "observed_sharpe": float(observed_sharpe),
        "expected_max_sharpe": float(benchmark),
        "n_trials": n_trials,
        "n_observations": n_observations,
        "sharpe_std": float(sharpe_std),
        "skewness": float(skewness),
        "kurtosis_pearson": float(kurtosis),
        "assumption": "IID approximation; independent trials",
    }
