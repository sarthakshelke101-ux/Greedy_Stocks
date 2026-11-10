"""Append-only JSONL registry for reproducible strategy trials."""

import json
import math
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "database" / "processed" / "analytics" / "trial_registry.jsonl"
)


def _finite_number(value):
    try:
        result = float(value)
    except (TypeError, ValueError):
        return False
    return math.isfinite(result)


def _acquire_lock(lock_path, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return lock_path.open("x", encoding="utf-8")
        except FileExistsError:
            time.sleep(0.05)
    raise TimeoutError(f"Registry lock timeout: {lock_path}")


def append_trial(
    algorithm,
    config,
    daily_returns,
    dates=None,
    metadata=None,
    trial_id=None,
    path=None,
):
    """Append one immutable trial record. Duplicate IDs are rejected."""

    if not isinstance(algorithm, str) or not algorithm.strip():
        raise ValueError("algorithm must be a non-empty string")
    if not isinstance(config, dict):
        raise ValueError("config must be a dictionary")

    returns = [float(x) for x in daily_returns]
    if len(returns) < 2 or not all(math.isfinite(x) for x in returns):
        raise ValueError("daily_returns must contain at least two finite values")

    if dates is not None:
        dates = [str(x) for x in dates]
        if len(dates) != len(returns):
            raise ValueError("dates and daily_returns lengths must match")
        if len(set(dates)) != len(dates):
            raise ValueError("dates must be unique")

    trial_id = str(trial_id or uuid.uuid4())
    target = Path(path) if path else DEFAULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_suffix(target.suffix + ".lock")

    record = {
        "schema_version": 1,
        "trial_id": trial_id,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "algorithm": algorithm.strip(),
        "config": config,
        "dates": dates,
        "daily_returns": returns,
        "observations": len(returns),
        "metadata": metadata or {},
    }

    # Validate JSON serialization before acquiring the lock.
    line = json.dumps(record, sort_keys=True, allow_nan=False)

    lock = _acquire_lock(lock_path)
    try:
        if target.exists():
            with target.open("r", encoding="utf-8") as existing:
                for raw in existing:
                    if not raw.strip():
                        continue
                    previous = json.loads(raw)
                    if previous.get("trial_id") == trial_id:
                        raise ValueError(f"Duplicate trial_id: {trial_id}")

        with target.open("a", encoding="utf-8", newline="\n") as output:
            output.write(line + "\n")
            output.flush()
    finally:
        lock.close()
        lock_path.unlink(missing_ok=True)

    return record


def read_trials(path=None):
    """Read registry records without modifying the registry."""
    target = Path(path) if path else DEFAULT_PATH
    if not target.exists():
        return []

    records = []
    with target.open("r", encoding="utf-8") as source:
        for line_number, raw in enumerate(source, start=1):
            if not raw.strip():
                continue
            try:
                records.append(json.loads(raw))
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid registry JSON at line {line_number}"
                ) from exc
    return records
