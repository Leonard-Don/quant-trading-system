from src.analytics.industry_stock_details import (
    backfill_stock_details_with_valuation,
    extract_stock_detail_fields,
)


def test_extract_stock_detail_fields_reads_turnover_aliases():
    detail = extract_stock_detail_fields({
        "symbol": "600000",
        "name": "浦发银行",
        "turnoverRatio": 3.2,
    })

    assert detail["turnover_rate"] == 3.2
    assert detail["turnover"] == 3.2


def test_backfill_stock_details_with_valuation_populates_turnover():
    class DummyProvider:
        def get_stock_valuation(self, symbol):
            assert symbol == "600000"
            return {
                "market_cap": 2_157_900_000_000,
                "pe_ttm": 5.4,
                "turnover": 1.86,
            }

    enriched = backfill_stock_details_with_valuation([
        {
            "symbol": "600000",
            "name": "浦发银行",
            "market_cap": None,
            "pe_ratio": None,
            "turnover_rate": None,
        }
    ], DummyProvider())

    assert enriched[0]["market_cap"] == 2_157_900_000_000
    assert enriched[0]["pe_ratio"] == 5.4
    assert enriched[0]["turnover_rate"] == 1.86
    assert enriched[0]["turnover"] == 1.86
