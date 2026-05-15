"""Unit tests for the ETF rotation data helpers.

Covers parsing of upstream feeds (Sina hq_str + Eastmoney fundgz) and the
pure portfolio helpers (weights / trade suggestions). Tests must NOT touch
the network — fixtures are inline strings.
"""

from __future__ import annotations

import math

import pytest

from src.data.etf_rotation import (
    DEFAULT_UNIVERSE,
    EtfHolding,
    EtfQuote,
    EtfTradeSuggestion,
    EtfUniverseItem,
    build_trade_suggestions,
    calculate_current_weights,
    parse_fundgz,
    parse_fundgz_to_nav,
    parse_sina_quotes,
)


# ---------------------------------------------------------------------------
# Fixtures (inline so the tests stay hermetic)
# ---------------------------------------------------------------------------

SINA_510300 = (
    'var hq_str_sh510300="华泰柏瑞300ETF,3.821,3.815,3.851,3.871,3.810,3.851,3.852,'
    "68384528,263432854.000,1500,3.851,2300,3.850,4100,3.849,5300,3.848,6700,3.847,"
    "2400,3.852,3300,3.853,4600,3.854,5500,3.855,6900,3.856,"
    '2026-05-13,15:00:03,00,";'
)

SINA_513130 = (
    'var hq_str_sh513130="恒生科技ETF,0.992,0.985,1.012,1.015,0.988,1.011,1.012,'
    "1234567890,1345678900.000,100,1.011,200,1.010,300,1.009,400,1.008,500,1.007,"
    "150,1.012,250,1.013,350,1.014,450,1.015,550,1.016,"
    '2026-05-13,15:00:03,00,";'
)

SINA_BATCH = SINA_510300 + "\n" + SINA_513130

FUNDGZ_159985 = (
    'jsonpgz({"fundcode":"159985","name":"华夏饲料豆粕期货ETF",'
    '"jzrq":"2026-05-12","dwjz":"1.4321","gsz":"1.4456","gszzl":"0.94",'
    '"gztime":"2026-05-13 15:00"});'
)


def _holdings_seed() -> list[EtfHolding]:
    """A deterministic portfolio that mirrors a typical screenshot."""
    return [
        EtfHolding(code="159985", name="豆粕ETF", shares=10000, cost_price=1.40,
                   current_price=1.50),
        EtfHolding(code="512400", name="有色金属ETF", shares=17500, cost_price=1.85,
                   current_price=2.00),
        EtfHolding(code="510300", name="沪深300ETF", shares=1000, cost_price=4.20,
                   current_price=5.00),
        EtfHolding(code="518680", name="黄金ETF基金", shares=7000, cost_price=4.10,
                   current_price=5.00),
        EtfHolding(code="513130", name="恒生科技ETF", shares=10000, cost_price=0.95,
                   current_price=1.00),
    ]


# ---------------------------------------------------------------------------
# Universe
# ---------------------------------------------------------------------------

def test_default_universe_exposes_expected_codes():
    codes = [item.code for item in DEFAULT_UNIVERSE]
    assert codes == ["159985", "512400", "510300", "518680", "513130"]
    assert all(isinstance(item, EtfUniverseItem) for item in DEFAULT_UNIVERSE)
    # Every entry has an exchange prefix usable by Sina.
    assert all(item.exchange in {"sh", "sz"} for item in DEFAULT_UNIVERSE)


def test_default_universe_has_human_readable_names():
    names = {item.code: item.name for item in DEFAULT_UNIVERSE}
    assert "豆粕" in names["159985"]
    assert "300" in names["510300"]
    assert "恒生" in names["513130"] or "恒科" in names["513130"]


# ---------------------------------------------------------------------------
# Sina quote parsing
# ---------------------------------------------------------------------------

def test_parse_sina_quote_510300_shape():
    parsed = parse_sina_quotes(SINA_510300)
    assert "510300" in parsed

    quote = parsed["510300"]
    assert isinstance(quote, EtfQuote)
    assert quote.code == "510300"
    assert "300" in quote.name
    assert math.isclose(quote.open_price, 3.821, abs_tol=1e-6)
    assert math.isclose(quote.prev_close, 3.815, abs_tol=1e-6)
    assert math.isclose(quote.current_price, 3.851, abs_tol=1e-6)
    assert math.isclose(quote.high, 3.871, abs_tol=1e-6)
    assert math.isclose(quote.low, 3.810, abs_tol=1e-6)
    assert quote.volume == pytest.approx(68384528)
    assert quote.amount == pytest.approx(263432854.0)
    assert quote.date == "2026-05-13"


def test_parse_sina_quote_513130_shape():
    parsed = parse_sina_quotes(SINA_513130)
    quote = parsed["513130"]
    assert math.isclose(quote.current_price, 1.012, abs_tol=1e-6)
    assert math.isclose(quote.prev_close, 0.985, abs_tol=1e-6)
    # change_pct convenience derived from prev_close.
    expected_pct = (1.012 - 0.985) / 0.985
    assert quote.change_pct == pytest.approx(expected_pct, abs=1e-6)


def test_parse_sina_quotes_batch_returns_all_entries():
    parsed = parse_sina_quotes(SINA_BATCH)
    assert set(parsed.keys()) == {"510300", "513130"}


def test_parse_sina_quotes_skips_empty_payload():
    raw = 'var hq_str_sh510300="";'
    assert parse_sina_quotes(raw) == {}


def test_parse_sina_quotes_returns_empty_for_garbage():
    assert parse_sina_quotes("not a quote at all") == {}
    assert parse_sina_quotes("") == {}


# ---------------------------------------------------------------------------
# fundgz parsing
# ---------------------------------------------------------------------------

def test_parse_fundgz_returns_full_payload():
    data = parse_fundgz(FUNDGZ_159985)
    assert data is not None
    assert data["fundcode"] == "159985"
    assert data["dwjz"] == "1.4321"
    assert data["gsz"] == "1.4456"
    assert data["gszzl"] == "0.94"


def test_parse_fundgz_to_nav_extracts_floats():
    nav = parse_fundgz_to_nav(FUNDGZ_159985)
    assert nav is not None
    assert nav["code"] == "159985"
    assert math.isclose(nav["estimated_nav"], 1.4456, abs_tol=1e-6)
    assert math.isclose(nav["prev_nav"], 1.4321, abs_tol=1e-6)
    assert math.isclose(nav["change_pct"], 0.0094, abs_tol=1e-6)


def test_parse_fundgz_returns_none_on_garbage():
    assert parse_fundgz("not jsonpgz at all") is None
    assert parse_fundgz("jsonpgz(   );") is None
    assert parse_fundgz_to_nav("nope") is None


# ---------------------------------------------------------------------------
# Premium / discount
# ---------------------------------------------------------------------------

def test_etf_quote_premium_when_nav_present():
    quote = EtfQuote(
        code="510300", name="沪深300ETF", current_price=5.00,
        prev_close=4.95, estimated_nav=4.95,
    )
    # 5 / 4.95 - 1 ≈ 0.01010101
    assert quote.premium == pytest.approx((5.00 - 4.95) / 4.95, abs=1e-9)


def test_etf_quote_discount_when_quote_below_nav():
    quote = EtfQuote(
        code="518680", name="黄金ETF基金", current_price=4.50,
        prev_close=4.55, estimated_nav=4.55,
    )
    assert quote.premium == pytest.approx((4.50 - 4.55) / 4.55, abs=1e-9)
    assert quote.premium < 0


def test_etf_quote_premium_is_none_without_nav():
    quote = EtfQuote(code="510300", name="x", current_price=5.0, prev_close=4.9)
    assert quote.premium is None


def test_etf_quote_premium_is_none_without_price():
    quote = EtfQuote(code="510300", name="x", current_price=None,
                     prev_close=4.9, estimated_nav=4.95)
    assert quote.premium is None


# ---------------------------------------------------------------------------
# Current weights
# ---------------------------------------------------------------------------

def test_calculate_current_weights_matches_screenshot_seed():
    holdings = _holdings_seed()
    weights = calculate_current_weights(holdings, total_asset=100_000.0)

    assert weights["159985"] == pytest.approx(0.15, abs=1e-6)
    assert weights["512400"] == pytest.approx(0.35, abs=1e-6)
    assert weights["510300"] == pytest.approx(0.05, abs=1e-6)
    assert weights["518680"] == pytest.approx(0.35, abs=1e-6)
    assert weights["513130"] == pytest.approx(0.10, abs=1e-6)
    # Weights should sum to ~1.0 when total_asset matches sum of values.
    assert sum(weights.values()) == pytest.approx(1.0, abs=1e-6)


def test_calculate_current_weights_handles_zero_total_asset():
    holdings = _holdings_seed()
    weights = calculate_current_weights(holdings, total_asset=0.0)
    # All zeros instead of ZeroDivisionError.
    assert set(weights.values()) == {0.0}


def test_calculate_current_weights_handles_empty():
    assert calculate_current_weights([], total_asset=100.0) == {}


# ---------------------------------------------------------------------------
# Trade suggestions
# ---------------------------------------------------------------------------

def _quotes_seed() -> dict[str, EtfQuote]:
    return {
        "159985": EtfQuote(code="159985", name="豆粕ETF", current_price=1.50,
                           prev_close=1.48),
        "512400": EtfQuote(code="512400", name="有色金属ETF", current_price=2.00,
                           prev_close=2.02),
        "510300": EtfQuote(code="510300", name="沪深300ETF", current_price=5.00,
                           prev_close=4.95),
        "518680": EtfQuote(code="518680", name="黄金ETF基金", current_price=5.00,
                           prev_close=5.05),
        "513130": EtfQuote(code="513130", name="恒生科技ETF", current_price=1.00,
                           prev_close=0.99),
    }


def _by_code(suggestions: list[EtfTradeSuggestion]) -> dict[str, EtfTradeSuggestion]:
    return {s.code: s for s in suggestions}


def test_build_trade_suggestions_reduce_512400_and_518680():
    """512400 and 518680 are 35% each vs 20% targets → must be sells."""
    target = {
        "159985": 0.125,
        "512400": 0.20,
        "510300": 0.25,
        "518680": 0.20,
        "513130": 0.225,
    }
    out = build_trade_suggestions(
        current_holdings=_holdings_seed(),
        target_weights=target,
        quotes=_quotes_seed(),
        total_asset=100_000.0,
    )
    by_code = _by_code(out)

    assert by_code["512400"].action == "sell"
    # Need to release 15% × 100k = 15,000 at 2.00 → 7,500 shares (lot of 100).
    assert by_code["512400"].shares == 7500

    assert by_code["518680"].action == "sell"
    assert by_code["518680"].shares == 3000  # 15,000 / 5.00


def test_build_trade_suggestions_holds_dou_po_within_threshold():
    """159985 is 15% vs 12.5% target — delta 2.5% sits inside the 3% threshold."""
    target = {
        "159985": 0.125,
        "512400": 0.20,
        "510300": 0.25,
        "518680": 0.20,
        "513130": 0.225,
    }
    out = build_trade_suggestions(
        current_holdings=_holdings_seed(),
        target_weights=target,
        quotes=_quotes_seed(),
        total_asset=100_000.0,
    )
    by_code = _by_code(out)
    assert by_code["159985"].action == "hold"
    assert by_code["159985"].shares == 0


def test_build_trade_suggestions_adds_510300_and_513130_when_target_above():
    target = {
        "159985": 0.125,
        "512400": 0.20,
        "510300": 0.25,
        "518680": 0.20,
        "513130": 0.225,
    }
    out = build_trade_suggestions(
        current_holdings=_holdings_seed(),
        target_weights=target,
        quotes=_quotes_seed(),
        total_asset=100_000.0,
    )
    by_code = _by_code(out)

    assert by_code["510300"].action == "buy"
    # 20% × 100k = 20,000 at 5.00 → 4,000 shares.
    assert by_code["510300"].shares == 4000

    assert by_code["513130"].action == "buy"
    # 12.5% × 100k = 12,500 at 1.00 → 12,500 shares.
    assert by_code["513130"].shares == 12500


def test_build_trade_suggestions_threshold_can_promote_dou_po_to_sell():
    """When threshold is lowered, 豆粕's 2.5% drift turns into a sell."""
    target = {
        "159985": 0.125,
        "512400": 0.20,
        "510300": 0.25,
        "518680": 0.20,
        "513130": 0.225,
    }
    out = build_trade_suggestions(
        current_holdings=_holdings_seed(),
        target_weights=target,
        quotes=_quotes_seed(),
        total_asset=100_000.0,
        threshold_weight=0.01,
    )
    by_code = _by_code(out)
    assert by_code["159985"].action == "sell"
    # 2.5% × 100k = 2,500 at 1.50 → 1666 → floor to lot 100 → 1,600.
    assert by_code["159985"].shares == 1600


def test_build_trade_suggestions_rounds_to_lot_size():
    """A 4% drift on 513130 produces a buy whose shares are a multiple of 100."""
    target = {
        "159985": 0.15,
        "512400": 0.35,
        "510300": 0.05,
        "518680": 0.31,  # +4% delta → triggers a small buy
        "513130": 0.14,  # +4% delta on a 1.00 quote
    }
    out = build_trade_suggestions(
        current_holdings=_holdings_seed(),
        target_weights=target,
        quotes=_quotes_seed(),
        total_asset=100_000.0,
    )
    by_code = _by_code(out)
    for code in ("518680", "513130"):
        suggestion = by_code[code]
        if suggestion.action != "hold":
            assert suggestion.shares % 100 == 0


def test_build_trade_suggestions_custom_lot_size_round_lots():
    out = build_trade_suggestions(
        current_holdings=_holdings_seed(),
        target_weights={"510300": 0.25, "159985": 0.15, "512400": 0.35,
                        "518680": 0.20, "513130": 0.05},
        quotes=_quotes_seed(),
        total_asset=100_000.0,
        lot_size=500,
    )
    by_code = _by_code(out)
    for suggestion in by_code.values():
        if suggestion.action != "hold":
            assert suggestion.shares % 500 == 0


def test_build_trade_suggestions_handles_missing_quote_as_hold():
    holdings = _holdings_seed()
    quotes = _quotes_seed()
    del quotes["510300"]
    target = {"510300": 0.25, "159985": 0.15, "512400": 0.20,
              "518680": 0.20, "513130": 0.20}
    out = build_trade_suggestions(
        current_holdings=holdings, target_weights=target,
        quotes=quotes, total_asset=100_000.0,
    )
    by_code = _by_code(out)
    # Without a quote we cannot size the order; downgrade to hold.
    assert by_code["510300"].action == "hold"


def test_build_trade_suggestions_buys_when_target_introduces_new_etf():
    holdings = [h for h in _holdings_seed() if h.code != "513130"]
    target = {"159985": 0.15, "512400": 0.35, "510300": 0.05, "518680": 0.35,
              "513130": 0.10}
    out = build_trade_suggestions(
        current_holdings=holdings,
        target_weights=target,
        quotes=_quotes_seed(),
        total_asset=100_000.0,
    )
    by_code = _by_code(out)
    assert by_code["513130"].action == "buy"
    assert by_code["513130"].shares == 10000  # 10% × 100k / 1.00


def test_build_trade_suggestions_below_lot_size_becomes_hold():
    """When the rounded order would be 0 lots, the suggestion is hold."""
    out = build_trade_suggestions(
        current_holdings=_holdings_seed(),
        target_weights={"159985": 0.149, "512400": 0.35, "510300": 0.05,
                        "518680": 0.35, "513130": 0.101},
        quotes=_quotes_seed(),
        total_asset=100_000.0,
        # Threshold low enough to clear the gate, but the dollar drift is tiny.
        threshold_weight=0.0005,
        lot_size=1000,
    )
    by_code = _by_code(out)
    # 0.1% drift on 100k = 100. At 1.50 that's 66 shares → 0 lots of 1000.
    assert by_code["159985"].action == "hold"
    assert by_code["159985"].shares == 0


def test_build_trade_suggestions_caps_sell_at_current_holding_shares():
    """A 'sell' suggestion must never request more shares than the holding has.

    The order is sized from ``abs(delta) * total_asset / quote_price``, where
    ``total_asset`` reflects the position snapshot (using ``holding.current_price``)
    but ``quote_price`` is the live quote. Whenever the live quote drifts below
    the snapshot price, this ratio overshoots ``holding.shares`` — a manual
    user cannot fill the over-sized order. Lock in the invariant: a sell
    suggestion's share count is bounded by the actual position.
    """
    # 1000 shares at the snapshot price 5.00 → market_value 5000.
    holding = EtfHolding(
        code="510300", name="沪深300ETF", shares=1000,
        cost_price=4.50, current_price=5.00,
    )
    # Live quote shows a lower price than the snapshot used for total_asset.
    quote = EtfQuote(
        code="510300", name="沪深300ETF",
        current_price=4.00, prev_close=4.10,
    )

    out = build_trade_suggestions(
        current_holdings=[holding],
        target_weights={"510300": 0.0},
        quotes={"510300": quote},
        total_asset=5000.0,
        lot_size=100,
        threshold_weight=0.01,
    )
    by_code = _by_code(out)

    assert by_code["510300"].action == "sell"
    # Naive sizing wants 1250 → rounded 1200 lots. Cap must keep us at the
    # holding's actual share count (1000), preserving the lot multiple.
    assert by_code["510300"].shares <= holding.shares, (
        f"sell suggestion overshot the position: got "
        f"{by_code['510300'].shares} shares vs {holding.shares} held"
    )
    assert by_code["510300"].shares % 100 == 0
