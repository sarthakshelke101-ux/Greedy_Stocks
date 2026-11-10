from analytics.ask_greedy.greedy_knowledge import discover_sources, build_greedy_knowledge_context

def test_source_discovery_returns_paths():
    paths = discover_sources()
    assert isinstance(paths, list)
    assert len(paths) <= 14

def test_knowledge_context_is_bounded():
    result = build_greedy_knowledge_context("Explain Greedy V2")
    assert isinstance(result, str)
    assert len(result) <= 30000
    assert "GREEDY STOCKS SOURCE-CODE KNOWLEDGE" in result or "GREEDY SOURCE STATUS" in result

def test_source_files_are_project_local():
    from pathlib import Path
    root = Path.cwd().resolve()
    for path in discover_sources():
        assert root in path.resolve().parents
