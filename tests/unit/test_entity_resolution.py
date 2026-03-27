from src.data.alternative.entity_resolution import aggregate_entities, resolve_entity


def test_resolve_entity_normalizes_company_aliases():
    entity = resolve_entity(
        raw_value={"company": "英伟达", "ticker": "NVDA"},
        tags=["AI算力"],
        headline="英伟达算力需求继续走强",
    )

    assert entity["canonical"] == "NVDA"
    assert entity["entity_type"] == "company"


def test_aggregate_entities_merges_same_canonical_entity():
    rows = [
        {"canonical_entity": "NVDA", "entity_type": "company", "timestamp": "2026-03-20T10:00:00"},
        {"canonical_entity": "NVDA", "entity_type": "company", "timestamp": "2026-03-20T11:00:00"},
        {"canonical_entity": "GRID", "entity_type": "theme", "timestamp": "2026-03-20T09:00:00"},
    ]

    aggregated = aggregate_entities(rows, limit=5)
    assert aggregated[0]["entity"] == "NVDA"
    assert aggregated[0]["count"] == 2
