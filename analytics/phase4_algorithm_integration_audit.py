from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(".")
OUTPUT = Path("reports/phase4/algorithm_integration_audit.json")

SEARCH_DIRS = [
    "analytics", "backend", "tests",
    "reports", "experiments", "results",
]

PATTERNS = {
    "greedy_algorithm": r"greedy|portfolio.?selection|stock.?selection",
    "walk_forward": r"walk.?forward|out.?of.?sample|oos|fold",
    "experiments": r"experiment|backtest|benchmark|equal.?weight",
    "risk_metrics": r"sharpe|sortino|drawdown|volatility|risk.?free",
    "ask_greedy": r"ask.?greedy|research.?planner|chat_routes",
    "selection_explanations": r"selected|rejected|eligibility|ranking|score|allocation",
}

SKIP_DIRS = {
    ".venv", "__pycache__", ".git", "node_modules",
    "site-packages", "dist", "build",
}

EXTENSIONS = {".py", ".json", ".csv", ".md", ".txt", ".yaml", ".yml"}


def main():
    files = []
    matches = {key: [] for key in PATTERNS}
    errors = []

    for folder in SEARCH_DIRS:
        base = ROOT / folder
        if not base.exists():
            continue

        for path in base.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue

            try:
                content = path.read_text(encoding="utf-8-sig", errors="replace")
            except Exception as exc:
                errors.append({"file": str(path), "error": str(exc)})
                continue

            relative = str(path).replace("\\", "/")
            lines = content.splitlines()

            files.append({
                "path": relative,
                "size_bytes": path.stat().st_size,
                "lines": len(lines),
            })

            for category, expression in PATTERNS.items():
                found = [
                    {"line": n, "text": line.strip()[:240]}
                    for n, line in enumerate(lines, 1)
                    if re.search(expression, line, re.I)
                ]
                if found:
                    matches[category].append({
                        "file": relative,
                        "match_count": len(found),
                        "matches": found[:35],
                    })

    important = [
        "backend/chat_routes.py",
        "analytics/ask_greedy/research_planner.py",
        "analytics/ask_greedy/historical_intelligence.py",
    ]

    entry_points = {}
    for name in important:
        path = ROOT / name
        entry_points[name] = (
            {
                "exists": True,
                "lines": path.read_text(
                    encoding="utf-8-sig", errors="replace"
                ).splitlines()[:100],
            }
            if path.exists()
            else {"exists": False}
        )

    report = {
        "audit": "GREEDY STOCKS Phase 4 algorithm integration discovery",
        "read_only": True,
        "file_count": len(files),
        "files": files,
        "categories": matches,
        "entry_points": entry_points,
        "scan_errors": errors,
        "requirements": [
            "Explain the actual implemented GREEDY algorithm.",
            "Compare against conventional baselines on identical data and dates.",
            "Explain selected and rejected stocks using recorded decision inputs.",
            "Use saved experiment and walk-forward evidence accurately.",
            "Keep in-sample and out-of-sample results separate.",
            "Preserve risk-free-rate assumptions and metric definitions.",
        ],
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\nFILES DISCOVERED:", len(files))
    for category, entries in matches.items():
        print(f"\n{category.upper()}: {len(entries)} files")
        for item in entries[:15]:
            print(" ", item["file"], "-", item["match_count"], "matches")

    print("\nENTRY POINTS")
    for name, info in entry_points.items():
        print(name, "FOUND" if info["exists"] else "NOT FOUND")

    print("\nSCAN ERRORS:", len(errors))
    print("REPORT:", OUTPUT)


if __name__ == "__main__":
    main()
