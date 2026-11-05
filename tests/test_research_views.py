from ui.research import coverage, filter_evidence, review_counts, search_view


def row(key, status, value="value", match="matched"):
    return {"id": key, "source_id": "s", "field_id": key, "value": value,
            "review": {"status": status, "edited_value": "Corrected value" if status == "edit" else None},
            "match_status": match, "locators": [{"quote": "Original passage"}]}


def test_hold_and_location_do_not_count_as_human_acceptance():
    rows = [row("a", "pending"), row("b", "hold"), row("c", "edit"),
            row("d", "reject"), row("e", "pending", None, "not_found")]
    counts = review_counts(rows)
    assert counts["resolved"] == 2 and counts["kept"] == 1
    assert counts["pending"] == 2 and counts["held"] == 1 and counts["missing"] == 1
    result = coverage(rows, [{"id": "s"}, {"id": "new"}], [{"id": "c", "name": "Field"}])
    assert result[0]["채택"] == 1 and result[0]["추출 대기"] == 1


def test_filter_uses_corrected_values_and_quotes_without_changing_data():
    rows = [row("a", "edit"), row("b", "hold", match="needs_check")]
    sources = [{"id": "s", "title": "Paper", "bib": {"authors": ["Park"], "year": 2025}}]
    assert filter_evidence(rows, sources, "Park corrected", "채택") == rows[:1]
    assert filter_evidence(rows, sources, "Original", "위치 미확인") == rows[1:]
    assert filter_evidence(rows, sources, field_ids=set()) == []
    assert filter_evidence(rows, sources, "absent") == []


def test_search_sort_handles_unknown_metadata_without_mutation():
    results = [{"title": "A", "authors": [], "year": None, "cited_by": None},
               {"title": "B", "authors": [], "year": 2025, "cited_by": 10, "oa": True}]
    assert search_view(results, order="최신순")[0]["title"] == "B"
    assert search_view(results, order="피인용순")[0]["title"] == "B"
    assert len(search_view(results, oa_only=True)) == 1
    assert results[0]["title"] == "A"
