"""A-share / ETF historical data should be served by Tushare first.

For Shanghai/Shenzhen stocks and ETFs, Tushare is both faster (~0.1s vs ~0.85s
through the Yahoo ``.SS``/``.SZ`` path) and more complete/accurate — it is the
authoritative A-share after-close source. Two things make that work:

1. ``TushareProvider.normalize_symbol`` must accept the system's Yahoo-style
   ``.SS`` Shanghai suffix and map it to Tushare's ``.SH`` ts_code, otherwise
   every Shanghai symbol/ETF silently returns an empty frame.
2. ``DataProviderFactory`` must promote Tushare to the front of the provider
   fall-through *for A-share/ETF symbols only* — it stays low priority (45,
   paid + rate-limited) for US/global symbols.
"""

from src.data.providers.provider_factory import DataProviderFactory
from src.data.providers.tushare_provider import TushareProvider


class TestNormalizeYahooShanghaiSuffix:
    def test_ss_suffix_maps_to_sh(self):
        # Yahoo/this system uses .SS for Shanghai; Tushare ts_code uses .SH.
        assert TushareProvider.normalize_symbol("600519.SS") == "600519.SH"
        assert TushareProvider.normalize_symbol("510300.SS") == "510300.SH"

    def test_ss_suffix_is_case_insensitive(self):
        assert TushareProvider.normalize_symbol("600519.ss") == "600519.SH"

    def test_existing_suffixes_unchanged(self):
        assert TushareProvider.normalize_symbol("000001.SZ") == "000001.SZ"
        assert TushareProvider.normalize_symbol("600519.SH") == "600519.SH"
        assert TushareProvider.normalize_symbol("430139.BJ") == "430139.BJ"

    def test_bare_six_digit_inference_unchanged(self):
        assert TushareProvider.normalize_symbol("600519") == "600519.SH"
        assert TushareProvider.normalize_symbol("000001") == "000001.SZ"


class TestFactoryAShareRouting:
    def _factory(self):
        # A dummy tushare token only registers the provider — the routing
        # methods under test never hit the Tushare API.
        return DataProviderFactory(
            {
                "default": "yahoo",
                "providers": ["yahoo", "us_stock", "tushare"],
                "api_keys": {"tushare": "test-token"},
                "fallback_enabled": True,
            }
        )

    def test_detects_a_share_and_etf_symbols(self):
        f = self._factory()
        for sym in [
            "600519.SS", "000001.SZ", "510300.SS", "600519.SH",
            "600519", "000001", "SH600519", "430139.BJ",
        ]:
            assert f._is_a_share_symbol(sym), sym

    def test_rejects_non_a_share_symbols(self):
        f = self._factory()
        for sym in ["AAPL", "MSFT", "^GSPC", "BTC-USD", "GC=F", ""]:
            assert not f._is_a_share_symbol(sym), sym

    def test_a_share_stock_promotes_tushare_first(self):
        f = self._factory()
        order = f._ordered_providers_for_symbol("600519.SS")
        assert order[0].name == "tushare"

    def test_etf_promotes_tushare_first(self):
        f = self._factory()
        order = f._ordered_providers_for_symbol("510300.SS")
        assert order[0].name == "tushare"

    def test_us_symbol_keeps_priority_order(self):
        f = self._factory()
        order = f._ordered_providers_for_symbol("AAPL")
        # Tushare (paid, priority 45) must not lead for US/global symbols.
        assert order[0].name != "tushare"
        assert order[0].priority <= 1

    def test_ordering_is_a_permutation_of_all_providers(self):
        f = self._factory()
        base = {p.name for p in f.get_sorted_providers()}
        reordered = {p.name for p in f._ordered_providers_for_symbol("600519.SS")}
        assert reordered == base
