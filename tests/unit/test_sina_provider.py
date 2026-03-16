import json
from pathlib import Path
from unittest.mock import MagicMock

from src.data.providers.sina_provider import SinaFinanceProvider


def test_get_industry_list_uses_persistent_cache_on_error(tmp_path):
    cache_path = tmp_path / "sina_industry_list_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-03-12T21:00:00",
                "data": [{"industry_name": "电力行业", "industry_code": "new_dlhy"}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    provider = SinaFinanceProvider()
    provider.session.get = MagicMock(side_effect=RuntimeError("blocked"))

    original_path = SinaFinanceProvider._industry_list_cache_path
    SinaFinanceProvider._industry_list_cache_path = cache_path
    try:
        df = SinaFinanceProvider.get_industry_list.__wrapped__(provider)
    finally:
        SinaFinanceProvider._industry_list_cache_path = original_path

    assert not df.empty
    assert df.iloc[0]["industry_code"] == "new_dlhy"


def test_get_industry_stocks_uses_persistent_cache_on_error(tmp_path):
    cache_path = tmp_path / "sina_industry_stocks_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-03-12T21:00:00",
                "data": {
                    "new_dlhy": {
                        "updated_at": "2026-03-12T21:00:00",
                        "rows": [{"code": "600900", "name": "长江电力", "mktcap": 100}],
                    }
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    provider = SinaFinanceProvider()
    provider.session.get = MagicMock(side_effect=RuntimeError("blocked"))

    original_path = SinaFinanceProvider._industry_stocks_cache_path
    SinaFinanceProvider._industry_stocks_cache_path = cache_path
    try:
        stocks = provider.get_industry_stocks("new_dlhy")
    finally:
        SinaFinanceProvider._industry_stocks_cache_path = original_path

    assert stocks
    assert stocks[0]["code"] == "600900"


def test_persist_industry_stocks_merges_existing_entries(tmp_path):
    cache_path = tmp_path / "sina_industry_stocks_cache.json"
    original_path = SinaFinanceProvider._industry_stocks_cache_path
    SinaFinanceProvider._industry_stocks_cache_path = cache_path
    try:
        SinaFinanceProvider._persist_industry_stocks("new_dlhy", [{"code": "600900", "name": "长江电力"}])
        SinaFinanceProvider._persist_industry_stocks("new_gsgq", [{"code": "600333", "name": "长春燃气"}])
        payload = json.loads(cache_path.read_text(encoding="utf-8"))
    finally:
        SinaFinanceProvider._industry_stocks_cache_path = original_path

    assert sorted(payload["data"].keys()) == ["new_dlhy", "new_gsgq"]


def test_get_industry_list_falls_back_to_alternate_endpoint(tmp_path):
    provider = SinaFinanceProvider()

    class DummyResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"status={self.status_code}")

    provider.session.get = MagicMock(side_effect=[
        DummyResponse(456, ""),
        DummyResponse(200, 'var S_Finance_bankuai_industry = {"hangye_ZA01":"hangye_ZA01,农业,16,12.3,-0.05,-0.4,1166966325,9896547145,sh601118,7.613,8.340,0.590,海南橡胶"}'),
    ])

    original_path = SinaFinanceProvider._industry_list_cache_path
    SinaFinanceProvider._industry_list_cache_path = tmp_path / "sina_industry_list_cache.json"
    try:
        df = SinaFinanceProvider.get_industry_list.__wrapped__(provider)
    finally:
        SinaFinanceProvider._industry_list_cache_path = original_path

    assert not df.empty
    assert df.iloc[0]["industry_code"] == "hangye_ZA01"
    assert df.iloc[0]["industry_name"] == "农业"


def test_get_industry_list_prefers_cached_new_codes_over_hangye_fallback(tmp_path):
    cache_path = tmp_path / "sina_industry_list_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-03-12T21:00:00",
                "data": [{"industry_name": "电力行业", "industry_code": "new_dlhy"}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    provider = SinaFinanceProvider()

    class DummyResponse:
        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"status={self.status_code}")

    provider.session.get = MagicMock(side_effect=[
        DummyResponse(456, ""),
        DummyResponse(200, 'var S_Finance_bankuai_industry = {"hangye_ZA01":"hangye_ZA01,农业,16,12.3,-0.05,-0.4,1166966325,9896547145,sh601118,7.613,8.340,0.590,海南橡胶"}'),
    ])

    original_path = SinaFinanceProvider._industry_list_cache_path
    SinaFinanceProvider._industry_list_cache_path = cache_path
    try:
        df = SinaFinanceProvider.get_industry_list.__wrapped__(provider)
    finally:
        SinaFinanceProvider._industry_list_cache_path = original_path

    assert not df.empty
    assert df.iloc[0]["industry_code"] == "new_dlhy"
