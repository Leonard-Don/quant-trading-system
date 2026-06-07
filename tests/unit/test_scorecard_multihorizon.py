import importlib


def _reports(name, oos, passes, extra=None):
    base = {
        "name": name,
        "n_dates": 40,
        "mean_ic": oos,
        "icir": 0.3 if passes else 0.0,
        "oos_mean_ic": oos,
        "sign_stable": passes,
        "passes": passes,
        "yearly_ic": {2023: oos},
    }
    if extra:
        base.update(extra)
    return base


def test_parse_horizons():
    mod = importlib.import_module("scripts.run_factor_scorecard")
    assert mod.parse_horizons("5,20,60") == [5, 20, 60]
    assert mod.parse_horizons("20") == [20]
    assert mod.parse_horizons(" 5 , 10 ,5 ") == [5, 10]  # trimmed + de-duped, order kept
    assert mod.parse_horizons("") == []


def test_resolve_universe_default():
    mod = importlib.import_module("scripts.run_factor_scorecard")

    class _Prov:
        def get_index_constituents(self, code):
            raise AssertionError("default must not hit the network")

    syms = mod.resolve_universe("default", _Prov())
    assert syms == mod.DEFAULT_UNIVERSE
    assert "600519.SH" in syms


def test_resolve_universe_csi300_calls_index_weight():
    mod = importlib.import_module("scripts.run_factor_scorecard")

    calls = {}

    class _Prov:
        def get_index_constituents(self, code):
            calls["code"] = code
            return ["600519.SH", "000858.SZ"]

    syms = mod.resolve_universe("csi300", _Prov())
    assert syms == ["600519.SH", "000858.SZ"]
    assert calls["code"] == "000300.SH"


def test_build_oos_ic_matrix_markdown():
    mod = importlib.import_module("scripts.run_factor_scorecard")
    reports_by_h = {
        5: [_reports("roe", 0.01, False), _reports("momentum", 0.04, True)],
        20: [_reports("roe", 0.05, True), _reports("momentum", -0.02, False)],
    }
    md = mod.build_oos_ic_matrix_markdown(reports_by_h)
    # header has both horizons
    assert "h=5" in md and "h=20" in md
    # rows present for both factors with their OOS IC values
    assert "roe" in md and "momentum" in md
    assert "0.0500" in md  # roe @ h20
    assert "0.0400" in md  # momentum @ h5
    assert "-0.0200" in md  # momentum @ h20 (negative)


def test_build_pass_fail_matrix_markdown():
    mod = importlib.import_module("scripts.run_factor_scorecard")
    reports_by_h = {
        5: [_reports("roe", 0.01, False), _reports("momentum", 0.04, True)],
        20: [_reports("roe", 0.05, True), _reports("momentum", -0.02, False)],
    }
    md = mod.build_pass_fail_matrix_markdown(reports_by_h)
    assert "h=5" in md and "h=20" in md
    assert "roe" in md and "momentum" in md
    # PASS markers appear (✓ for momentum@5, roe@20)
    assert md.count("✓") == 2
    assert "✗" in md


def test_build_multi_horizon_markdown_sections_and_pass_summary():
    mod = importlib.import_module("scripts.run_factor_scorecard")
    reports_by_h = {
        5: [_reports("roe", 0.01, False), _reports("momentum", 0.04, True)],
        20: [_reports("roe", 0.05, True), _reports("momentum", -0.02, False)],
    }
    md = mod.build_multi_horizon_markdown(reports_by_h, universe_label="csi300", n_symbols=250)
    # a per-horizon section for each horizon
    assert "h=5" in md and "h=20" in md
    # universe metadata surfaced
    assert "csi300" in md and "250" in md
    # both matrices present
    assert "OOS IC" in md
    # honest pass summary: momentum@5 and roe@20 pass
    assert "momentum@5" in md and "roe@20" in md


def test_build_multi_horizon_markdown_nothing_passes():
    mod = importlib.import_module("scripts.run_factor_scorecard")
    reports_by_h = {
        5: [_reports("roe", 0.01, False)],
        20: [_reports("roe", -0.05, False)],
    }
    md = mod.build_multi_horizon_markdown(reports_by_h, universe_label="csi300", n_symbols=250)
    assert "无" in md or "none" in md.lower()  # honest "nothing passes" gate
