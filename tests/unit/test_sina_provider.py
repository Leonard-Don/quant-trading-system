import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.data.providers.sina_provider import SinaFinanceProvider


def test_load_json_cache_reuses_memory_when_file_unchanged(tmp_path):
    cache_path = tmp_path / "payload.json"
    cache_path.write_text(
        json.dumps({"updated_at": "2026-04-20T00:00:00", "data": {"foo": "bar"}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    original_memory = dict(SinaFinanceProvider._json_cache_memory)
    SinaFinanceProvider._json_cache_memory = {}

    try:
        first = SinaFinanceProvider._load_json_cache(cache_path)
        with patch.object(Path, "read_text", side_effect=AssertionError("read_text should not run on warm load")):
            second = SinaFinanceProvider._load_json_cache(cache_path)
    finally:
        SinaFinanceProvider._json_cache_memory = original_memory

    assert first == {"updated_at": "2026-04-20T00:00:00", "data": {"foo": "bar"}}
    assert second == first


def test_load_persistent_industry_list_reuses_dataframe_cache_when_file_unchanged(tmp_path):
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

    original_path = SinaFinanceProvider._industry_list_cache_path
    original_cache = dict(SinaFinanceProvider._persistent_industry_list_frame_cache)
    SinaFinanceProvider._industry_list_cache_path = cache_path
    SinaFinanceProvider._persistent_industry_list_frame_cache = {}

    try:
        first = SinaFinanceProvider._load_persistent_industry_list()
        with patch.object(
            SinaFinanceProvider,
            "_load_json_cache",
            side_effect=AssertionError("_load_json_cache should not run on warm industry list load"),
        ):
            second = SinaFinanceProvider._load_persistent_industry_list()
    finally:
        SinaFinanceProvider._industry_list_cache_path = original_path
        SinaFinanceProvider._persistent_industry_list_frame_cache = original_cache

    assert not first.empty
    assert second.iloc[0]["industry_code"] == "new_dlhy"


def test_get_persistent_industry_list_lookup_reuses_rows_cache_when_file_unchanged(tmp_path):
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

    original_path = SinaFinanceProvider._industry_list_cache_path
    original_cache = dict(SinaFinanceProvider._persistent_industry_list_lookup_cache)
    SinaFinanceProvider._industry_list_cache_path = cache_path
    SinaFinanceProvider._persistent_industry_list_lookup_cache = {}

    try:
        first = SinaFinanceProvider._get_persistent_industry_list_lookup()
        with patch.object(
            SinaFinanceProvider,
            "_load_json_cache",
            side_effect=AssertionError("_load_json_cache should not run on warm industry lookup load"),
        ):
            second = SinaFinanceProvider._get_persistent_industry_list_lookup()
    finally:
        SinaFinanceProvider._industry_list_cache_path = original_path
        SinaFinanceProvider._persistent_industry_list_lookup_cache = original_cache

    assert first["电力行业"][0]["industry_code"] == "new_dlhy"
    assert second["电力行业"][0]["industry_code"] == "new_dlhy"


def test_get_persistent_industry_list_lookup_cold_path_avoids_load_json_cache(tmp_path):
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

    original_path = SinaFinanceProvider._industry_list_cache_path
    original_cache = dict(SinaFinanceProvider._persistent_industry_list_lookup_cache)
    SinaFinanceProvider._industry_list_cache_path = cache_path
    SinaFinanceProvider._persistent_industry_list_lookup_cache = {}

    try:
        with patch.object(
            SinaFinanceProvider,
            "_load_json_cache",
            side_effect=AssertionError("_load_json_cache should not run on cold industry lookup load"),
        ):
            lookup = SinaFinanceProvider._get_persistent_industry_list_lookup()
    finally:
        SinaFinanceProvider._industry_list_cache_path = original_path
        SinaFinanceProvider._persistent_industry_list_lookup_cache = original_cache

    assert lookup["电力行业"][0]["industry_code"] == "new_dlhy"


def test_load_persistent_industry_stocks_reuses_rows_cache_when_file_unchanged(tmp_path):
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

    original_path = SinaFinanceProvider._industry_stocks_cache_path
    original_cache = dict(SinaFinanceProvider._persistent_industry_stocks_rows_cache)
    SinaFinanceProvider._industry_stocks_cache_path = cache_path
    SinaFinanceProvider._persistent_industry_stocks_rows_cache = {}

    try:
        first = SinaFinanceProvider._load_persistent_industry_stocks("new_dlhy")
        with patch.object(
            SinaFinanceProvider,
            "_load_json_cache",
            side_effect=AssertionError("_load_json_cache should not run on warm industry stocks load"),
        ):
            second = SinaFinanceProvider._load_persistent_industry_stocks("new_dlhy")
    finally:
        SinaFinanceProvider._industry_stocks_cache_path = original_path
        SinaFinanceProvider._persistent_industry_stocks_rows_cache = original_cache

    assert first[0]["code"] == "600900"
    assert second[0]["code"] == "600900"


def test_get_persistent_industry_stock_rows_cold_path_avoids_load_json_cache(tmp_path):
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

    original_path = SinaFinanceProvider._industry_stocks_cache_path
    original_cache = dict(SinaFinanceProvider._persistent_industry_stocks_rows_cache)
    SinaFinanceProvider._industry_stocks_cache_path = cache_path
    SinaFinanceProvider._persistent_industry_stocks_rows_cache = {}

    try:
        with patch.object(
            SinaFinanceProvider,
            "_load_json_cache",
            side_effect=AssertionError("_load_json_cache should not run on cold industry-stock rows load"),
        ):
            rows = SinaFinanceProvider._get_persistent_industry_stock_rows("new_dlhy")
    finally:
        SinaFinanceProvider._industry_stocks_cache_path = original_path
        SinaFinanceProvider._persistent_industry_stocks_rows_cache = original_cache

    assert rows[0]["code"] == "600900"


def test_get_persistent_industry_stock_codes_reuses_rows_cache_when_file_unchanged(tmp_path):
    cache_path = tmp_path / "sina_industry_stocks_cache.json"
    cache_path.write_text(
        json.dumps(
            {
                "updated_at": "2026-03-12T21:00:00",
                "data": {
                    "new_dlhy": {
                        "updated_at": "2026-03-12T21:00:00",
                        "rows": [{"code": "600900", "name": "长江电力", "mktcap": 100}],
                    },
                    "hangye_ZA01": {
                        "updated_at": "2026-03-12T21:00:00",
                        "rows": [{"code": "600000", "name": "非 new 节点"}],
                    },
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    original_path = SinaFinanceProvider._industry_stocks_cache_path
    original_cache = dict(SinaFinanceProvider._persistent_industry_stocks_rows_cache)
    original_codes_cache = dict(SinaFinanceProvider._persistent_industry_stock_codes_cache)
    SinaFinanceProvider._industry_stocks_cache_path = cache_path
    SinaFinanceProvider._persistent_industry_stocks_rows_cache = {}
    SinaFinanceProvider._persistent_industry_stock_codes_cache = {}

    try:
        first = SinaFinanceProvider._get_persistent_industry_stock_codes()
        with patch.object(
            SinaFinanceProvider,
            "_load_json_cache",
            side_effect=AssertionError("_load_json_cache should not run on warm stock-codes load"),
        ):
            second = SinaFinanceProvider._get_persistent_industry_stock_codes()
    finally:
        SinaFinanceProvider._industry_stocks_cache_path = original_path
        SinaFinanceProvider._persistent_industry_stocks_rows_cache = original_cache
        SinaFinanceProvider._persistent_industry_stock_codes_cache = original_codes_cache

    assert first == {"new_dlhy"}
    assert second == {"new_dlhy"}


def test_get_persistent_industry_stock_codes_cold_path_avoids_load_json_cache(tmp_path):
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

    original_path = SinaFinanceProvider._industry_stocks_cache_path
    original_rows_cache = dict(SinaFinanceProvider._persistent_industry_stocks_rows_cache)
    original_codes_cache = dict(SinaFinanceProvider._persistent_industry_stock_codes_cache)
    SinaFinanceProvider._industry_stocks_cache_path = cache_path
    SinaFinanceProvider._persistent_industry_stocks_rows_cache = {}
    SinaFinanceProvider._persistent_industry_stock_codes_cache = {}

    try:
        with patch.object(
            SinaFinanceProvider,
            "_load_json_cache",
            side_effect=AssertionError("_load_json_cache should not run on cold stock-codes load"),
        ):
            codes = SinaFinanceProvider._get_persistent_industry_stock_codes()
    finally:
        SinaFinanceProvider._industry_stocks_cache_path = original_path
        SinaFinanceProvider._persistent_industry_stocks_rows_cache = original_rows_cache
        SinaFinanceProvider._persistent_industry_stock_codes_cache = original_codes_cache

    assert codes == {"new_dlhy"}


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
