"""Read-only source-code knowledge layer for Ask GREEDY."""
from pathlib import Path
import logging

logger = logging.getLogger("greedy_stocks_chat.knowledge")

ROOT = Path(__file__).resolve().parents[2]
ANALYTICS = ROOT / "analytics"

# Only trusted project source directories and explicit analytical modules.
MAX_FILES = 14
MAX_FILE_CHARS = 6500
MAX_TOTAL_CHARS = 28000

EXACT_FILES = [
    "greedy_v2_engine.py",
    "greedy_v2_data.py",
    "greedy_v2_splits.py",
    "financial_metrics.py",
    "portfolio_analytics.py",
    "portfolio_allocation.py",
]

def discover_sources():
    found = {}

    for name in EXACT_FILES:
        path = ANALYTICS / name
        if path.is_file():
            found[path.resolve()] = path

    # Discover versioned implementations without assuming their names.
    for path in ANALYTICS.rglob("*.py"):
        if not path.is_file():
            continue
        low = path.name.lower()
        if "greedy" in low and any(x in low for x in ("v1", "v2", "v3", "engine", "algorithm")):
            found[path.resolve()] = path

    # Also discover Greedy-named backend algorithm modules.
    backend = ROOT / "backend"
    if backend.exists():
        for path in backend.glob("*greedy*.py"):
            if path.is_file():
                found[path.resolve()] = path

    return sorted(found.values(), key=lambda p: str(p).lower())[:MAX_FILES]

def build_greedy_knowledge_context(question=""):
    """Return bounded source excerpts; never execute source code."""
    pieces = []
    total = 0

    for path in discover_sources():
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError) as exc:
            logger.warning("Could not read algorithm source %s: %s", path.name, exc)
            continue

        # Keep context bounded and avoid exposing unrelated oversized modules.
        excerpt = text[:MAX_FILE_CHARS]
        relative = path.relative_to(ROOT).as_posix()
        block = (
            f"\n--- SOURCE FILE: {relative} ---\n"
            f"{excerpt}\n"
            f"--- END SOURCE FILE: {relative} ---\n"
        )

        if total + len(block) > MAX_TOTAL_CHARS:
            break

        pieces.append(block)
        total += len(block)

    if not pieces:
        return (
            "GREEDY SOURCE STATUS: No matching algorithm source files were found. "
            "Do not invent version-specific implementation details."
        )

    return (
        "GREEDY STOCKS SOURCE-CODE KNOWLEDGE\n"
        "The following excerpts are read-only project source files. "
        "Use them as evidence when explaining algorithm implementation.\n"
        "Do not claim a version exists unless its source is present. "
        "Do not infer undocumented behaviour. If a file is truncated, "
        "say the available excerpt does not establish the missing detail.\n"
        + "".join(pieces)
    )
