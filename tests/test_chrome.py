"""The status vocabulary must cover every state the core can produce, with one label per state."""
from ui import chrome


def test_status_tables_cover_core_states():
    assert set(chrome.REVIEW) == {"pending", "accept", "edit", "hold", "reject"}
    assert set(chrome.MATCH) == {"matched", "needs_check", "not_found"}
    assert set(chrome.DECISION) == {"include", "exclude", "pending"}
    assert set(chrome.RUN_STATE) == {"awaiting_extraction", "review", "complete"}
    for table in (chrome.REVIEW, chrome.MATCH, chrome.DECISION, chrome.RUN_STATE):
        labels = [v[0] for v in table.values()]
        assert len(labels) == len(set(labels))
        # Red is reserved for error messages; a status never uses it.
        assert all(v[1] != "red" for v in table.values())


def test_short_keeps_short_titles():
    assert chrome.short("짧은 제목") == "짧은 제목"
    assert chrome.short("a" * 60, 10).endswith("…") and len(chrome.short("a" * 60, 10)) == 10
