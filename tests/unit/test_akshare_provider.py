import json
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from src.data.providers.akshare_provider import AKShareProvider


def test_get_industry_metadata_persists_snapshot(tmp_path):
    provider = AKShareProvider()
    provider._industry_meta_cache = None
    provider._industry_meta_cache_time = None

    cache_path = tmp_path / "industry_metadata_cache.json"
    raw_df = pd.DataFrame(
        [
            {"板块名称": "白酒Ⅱ", "总市值": 123.0, "换手率": 2.5, "涨跌幅": 1.2},
            {"板块名称": "证券Ⅱ", "总市值": 456.0, "换手率": 3.1, "涨跌幅": -0.3},
        ]
    )

    with patch.object(AKShareProvider, "_industry_meta_cache_path", cache_path), patch(
        "src.data.providers.akshare_provider.ak.stock_board_industry_name_em",
        return_value=raw_df,
    ):
        df = provider._get_industry_metadata()

    assert not df.empty
    assert cache_path.exists()
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    assert payload["data"]
    assert "updated_at" in payload


def test_get_industry_metadata_uses_persistent_snapshot_on_failure(tmp_path):
    cache_path = tmp_path / "industry_metadata_cache.json"
    snapshot_df = pd.DataFrame(
        [
            {
                "industry_name": "白酒",
                "original_name": "白酒Ⅱ",
                "total_market_cap": 123.0,
                "turnover_rate": 2.5,
                "change_pct_meta": 1.2,
            }
        ]
    )
    cache_path.write_text(
        json.dumps(
            {
                "updated_at": datetime.now().isoformat(),
                "data": snapshot_df.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    provider = AKShareProvider()
    provider._industry_meta_cache = None
    provider._industry_meta_cache_time = None

    with patch.object(AKShareProvider, "_industry_meta_cache_path", cache_path), patch(
        "src.data.providers.akshare_provider.ak.stock_board_industry_name_em",
        side_effect=RuntimeError("upstream unavailable"),
    ):
        df = provider._get_industry_metadata()

    assert not df.empty
    assert df.iloc[0]["industry_name"] == "白酒"
