"""ETF portfolio-level risk guardrails.

The rules here are intentionally deterministic and dependency-free so they can
be reused by backtests, rotation signals, and paper-trading handoff code.

Unit convention
---------------
All weight/premium/drawdown inputs are treated as **fractions** (``0.10`` =
10%). To stay forgiving with operators who paste in percentage forms, the
module also accepts whole-number percentages in the range ``(1, 100]`` —
e.g. ``25`` is normalised to ``0.25``. Anything outside that band (or with
``abs() > 100``) raises ``ValueError`` rather than silently rescaling, so a
"50% drawdown" cannot be misread as 0.5%.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any, Optional

WeightMap = Mapping[str, float]
MetadataMap = Mapping[str, Mapping[str, Any]]

EPSILON = 1e-12

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EtfRiskRuleConfig:
    """Configurable caps for ETF rotation portfolio risk rules."""

    max_single_weight: float = 0.30
    commodity_resource_bucket_cap: float = 0.55
    min_cash_weight: float = 0.10
    qdii_premium_veto: float = 0.02
    hard_premium_veto: float = 0.05
    drawdown_cut_threshold: float = 0.08
    drawdown_gross_exposure_multiplier: float = 0.75
    cash_symbol: str = "CASH"
    commodity_resource_markers: tuple[str, ...] = (
        "commodity",
        "commodities",
        "resource",
        "resources",
        "natural_resource",
        "natural_resources",
        "gold",
        "oil",
        "energy",
        "metal",
        "metals",
        "precious_metal",
        "precious_metals",
    )
    qdii_markers: tuple[str, ...] = (
        "qdii",
        "cross_border",
        "cross-border",
        "overseas",
        "global",
        "hong_kong",
        "hong-kong",
        "us",
        "usa",
    )


@dataclass(frozen=True)
class EtfRiskAdjustment:
    """One symbol-level adjustment made by the rule engine."""

    symbol: str
    before_weight: float
    after_weight: float
    reason: str


@dataclass(frozen=True)
class EtfRiskDecision:
    """Adjusted portfolio and explanations emitted by the rule engine."""

    adjusted_weights: dict[str, float]
    reasons: list[str] = field(default_factory=list)
    adjustments: list[EtfRiskAdjustment] = field(default_factory=list)


def apply_etf_portfolio_risk_rules(
    proposed_weights: WeightMap,
    current_weights: Optional[WeightMap] = None,
    asset_metadata: Optional[MetadataMap] = None,
    premium_percentages: Optional[WeightMap] = None,
    portfolio_drawdown: Optional[float] = None,
    config: Optional[EtfRiskRuleConfig] = None,
) -> EtfRiskDecision:
    """Apply ETF rotation portfolio risk rules to proposed target weights.

    Args:
        proposed_weights: Desired target weights by symbol. Values may be
            fractions such as ``0.25`` or percentages such as ``25``.
        current_weights: Current portfolio weights by symbol, used to detect
            proposed buys for premium vetoes.
        asset_metadata: Symbol metadata. Supported keys include ``category``,
            ``bucket``, ``asset_class``, ``tags``, and boolean flags such as
            ``is_qdii``.
        premium_percentages: Premiums by symbol. Values may be fractions such
            as ``0.03`` or percentages such as ``3``.
        portfolio_drawdown: Current portfolio drawdown. Values may be fractions
            such as ``0.09`` or percentages such as ``9``.
        config: Optional rule configuration.
    """

    cfg = config or EtfRiskRuleConfig()
    metadata = asset_metadata or {}
    current = _normalize_weight_map(current_weights or {})
    premiums = {
        symbol: _as_fraction(value)
        for symbol, value in (premium_percentages or {}).items()
        if value is not None
    }
    weights = _prepare_target_weights(proposed_weights, metadata, cfg)

    _warn_missing_metadata(weights, metadata, cfg)

    reasons: list[str] = []
    adjustments: list[EtfRiskAdjustment] = []

    _apply_premium_vetoes(weights, current, metadata, premiums, cfg, reasons, adjustments)
    _apply_single_name_cap(weights, metadata, cfg, reasons, adjustments)
    _apply_bucket_cap(weights, metadata, cfg, reasons, adjustments)
    _apply_cash_floor(weights, metadata, cfg, reasons, adjustments)
    _apply_drawdown_cut(
        weights,
        metadata,
        _as_optional_fraction(portfolio_drawdown),
        cfg,
        reasons,
        adjustments,
    )

    _drop_dust(weights)
    return EtfRiskDecision(adjusted_weights=dict(weights), reasons=reasons, adjustments=adjustments)


def enforce_etf_portfolio_risk_rules(
    proposed_weights: WeightMap,
    current_weights: Optional[WeightMap] = None,
    asset_metadata: Optional[MetadataMap] = None,
    premium_percentages: Optional[WeightMap] = None,
    portfolio_drawdown: Optional[float] = None,
    config: Optional[EtfRiskRuleConfig] = None,
) -> EtfRiskDecision:
    """Alias with a more rule-oriented name for call sites."""

    return apply_etf_portfolio_risk_rules(
        proposed_weights=proposed_weights,
        current_weights=current_weights,
        asset_metadata=asset_metadata,
        premium_percentages=premium_percentages,
        portfolio_drawdown=portfolio_drawdown,
        config=config,
    )


def _prepare_target_weights(
    proposed_weights: WeightMap,
    asset_metadata: MetadataMap,
    config: EtfRiskRuleConfig,
) -> dict[str, float]:
    weights = _normalize_weight_map(proposed_weights)
    cash_symbol = _cash_symbol(weights, asset_metadata, config)
    total = sum(weights.values())

    if total > 1.0 + EPSILON:
        scale = 1.0 / total
        for symbol in list(weights):
            weights[symbol] *= scale
        total = 1.0

    if total < 1.0 - EPSILON:
        weights[cash_symbol] = weights.get(cash_symbol, 0.0) + (1.0 - total)

    weights.setdefault(cash_symbol, 0.0)
    return weights


def _apply_premium_vetoes(
    weights: dict[str, float],
    current_weights: dict[str, float],
    asset_metadata: MetadataMap,
    premium_percentages: Mapping[str, float],
    config: EtfRiskRuleConfig,
    reasons: list[str],
    adjustments: list[EtfRiskAdjustment],
) -> None:
    cash_symbol = _cash_symbol(weights, asset_metadata, config)

    for symbol, premium in premium_percentages.items():
        before = weights.get(symbol, 0.0)
        current = current_weights.get(symbol, 0.0)
        if before <= current + EPSILON:
            continue

        hard_veto = premium >= config.hard_premium_veto - EPSILON
        qdii_veto = _is_qdii_or_commodity(symbol, asset_metadata, config) and (
            premium >= config.qdii_premium_veto - EPSILON
        )
        if not hard_veto and not qdii_veto:
            continue

        after = current
        weights[symbol] = after
        weights[cash_symbol] = weights.get(cash_symbol, 0.0) + (before - after)

        threshold = config.hard_premium_veto if hard_veto else config.qdii_premium_veto
        reason = (
            f"Premium veto for {symbol}: premium {premium:.2%} exceeds "
            f"{threshold:.2%}; target increase capped at current weight."
        )
        reasons.append(reason)
        adjustments.append(EtfRiskAdjustment(symbol, before, after, reason))


def _apply_single_name_cap(
    weights: dict[str, float],
    asset_metadata: MetadataMap,
    config: EtfRiskRuleConfig,
    reasons: list[str],
    adjustments: list[EtfRiskAdjustment],
) -> None:
    cash_symbol = _cash_symbol(weights, asset_metadata, config)

    for symbol in list(weights):
        if _is_cash(symbol, asset_metadata, config):
            continue
        before = weights.get(symbol, 0.0)
        if before <= config.max_single_weight + EPSILON:
            continue

        weights[symbol] = config.max_single_weight
        weights[cash_symbol] = weights.get(cash_symbol, 0.0) + (before - config.max_single_weight)
        reason = (
            f"Single ETF cap for {symbol}: reduced from {before:.2%} "
            f"to {config.max_single_weight:.2%}."
        )
        reasons.append(reason)
        adjustments.append(
            EtfRiskAdjustment(symbol, before, config.max_single_weight, reason)
        )


def _apply_bucket_cap(
    weights: dict[str, float],
    asset_metadata: MetadataMap,
    config: EtfRiskRuleConfig,
    reasons: list[str],
    adjustments: list[EtfRiskAdjustment],
) -> None:
    cash_symbol = _cash_symbol(weights, asset_metadata, config)
    bucket_symbols = [
        symbol
        for symbol, weight in weights.items()
        if weight > EPSILON and _is_commodity_resource(symbol, asset_metadata, config)
    ]
    bucket_total = sum(weights[symbol] for symbol in bucket_symbols)

    if bucket_total <= config.commodity_resource_bucket_cap + EPSILON:
        return

    scale = config.commodity_resource_bucket_cap / bucket_total
    freed_weight = 0.0
    reason = (
        "Commodity/resource bucket cap: reduced combined bucket from "
        f"{bucket_total:.2%} to {config.commodity_resource_bucket_cap:.2%}."
    )

    for symbol in bucket_symbols:
        before = weights[symbol]
        after = before * scale
        weights[symbol] = after
        freed_weight += before - after
        adjustments.append(EtfRiskAdjustment(symbol, before, after, reason))

    weights[cash_symbol] = weights.get(cash_symbol, 0.0) + freed_weight
    reasons.append(reason)


def _apply_cash_floor(
    weights: dict[str, float],
    asset_metadata: MetadataMap,
    config: EtfRiskRuleConfig,
    reasons: list[str],
    adjustments: list[EtfRiskAdjustment],
) -> None:
    cash_symbol = _cash_symbol(weights, asset_metadata, config)
    current_cash = weights.get(cash_symbol, 0.0)

    if current_cash >= config.min_cash_weight - EPSILON:
        return

    non_cash_symbols = [
        symbol
        for symbol, weight in weights.items()
        if weight > EPSILON and not _is_cash(symbol, asset_metadata, config)
    ]
    non_cash_total = sum(weights[symbol] for symbol in non_cash_symbols)
    if non_cash_total <= EPSILON:
        weights[cash_symbol] = config.min_cash_weight
        return

    cash_needed = config.min_cash_weight - current_cash
    scale = max(0.0, (non_cash_total - cash_needed) / non_cash_total)
    reason = f"Cash floor: raised cash from {current_cash:.2%} to {config.min_cash_weight:.2%}."

    for symbol in non_cash_symbols:
        before = weights[symbol]
        after = before * scale
        weights[symbol] = after
        adjustments.append(EtfRiskAdjustment(symbol, before, after, reason))

    weights[cash_symbol] = config.min_cash_weight
    reasons.append(reason)


def _apply_drawdown_cut(
    weights: dict[str, float],
    asset_metadata: MetadataMap,
    portfolio_drawdown: Optional[float],
    config: EtfRiskRuleConfig,
    reasons: list[str],
    adjustments: list[EtfRiskAdjustment],
) -> None:
    if portfolio_drawdown is None or portfolio_drawdown <= config.drawdown_cut_threshold + EPSILON:
        return

    cash_symbol = _cash_symbol(weights, asset_metadata, config)
    non_cash_symbols = [
        symbol
        for symbol, weight in weights.items()
        if weight > EPSILON and not _is_cash(symbol, asset_metadata, config)
    ]
    gross_before = sum(weights[symbol] for symbol in non_cash_symbols)
    if gross_before <= EPSILON:
        return

    multiplier = min(max(config.drawdown_gross_exposure_multiplier, 0.0), 1.0)
    gross_after = gross_before * multiplier
    freed_weight = gross_before - gross_after
    reason = (
        f"Drawdown cut: portfolio drawdown {portfolio_drawdown:.2%} exceeds "
        f"{config.drawdown_cut_threshold:.2%}; gross ETF exposure reduced "
        f"from {gross_before:.2%} to {gross_after:.2%}."
    )

    for symbol in non_cash_symbols:
        before = weights[symbol]
        after = before * multiplier
        weights[symbol] = after
        adjustments.append(EtfRiskAdjustment(symbol, before, after, reason))

    weights[cash_symbol] = weights.get(cash_symbol, 0.0) + freed_weight
    reasons.append(reason)


def _warn_missing_metadata(
    weights: Mapping[str, float],
    asset_metadata: MetadataMap,
    config: EtfRiskRuleConfig,
) -> None:
    """Log a warning for held symbols that have no risk metadata entry.

    Without metadata the bucket / QDII / cash classifiers all return false,
    so commodity-bucket caps and premium vetoes silently skip the symbol —
    a dangerous failure mode for a real-money rotation portfolio.
    """

    missing = [
        symbol
        for symbol, weight in weights.items()
        if weight > EPSILON
        and not _is_cash(symbol, asset_metadata, config)
        and not asset_metadata.get(symbol)
    ]
    if missing:
        logger.warning(
            "ETF rotation: %d symbol(s) have no risk metadata and will bypass "
            "bucket/premium checks: %s",
            len(missing),
            ", ".join(sorted(missing)),
        )


def _normalize_weight_map(weights: WeightMap) -> dict[str, float]:
    normalized: dict[str, float] = {}
    for symbol, raw_weight in weights.items():
        weight = _as_fraction(raw_weight)
        normalized[str(symbol)] = max(0.0, weight)
    return normalized


def _cash_symbol(
    weights: Mapping[str, float],
    asset_metadata: MetadataMap,
    config: EtfRiskRuleConfig,
) -> str:
    for symbol in weights:
        if _is_cash(symbol, asset_metadata, config):
            return symbol
    return config.cash_symbol


def _is_cash(symbol: str, asset_metadata: MetadataMap, config: EtfRiskRuleConfig) -> bool:
    if symbol.upper() == config.cash_symbol.upper():
        return True
    tokens = _metadata_tokens(symbol, asset_metadata)
    return bool(tokens & {"cash", "money_market", "money-market", "currency", "deposit"})


def _is_qdii_or_commodity(
    symbol: str,
    asset_metadata: MetadataMap,
    config: EtfRiskRuleConfig,
) -> bool:
    if _is_commodity_resource(symbol, asset_metadata, config):
        return True
    tokens = _metadata_tokens(symbol, asset_metadata)
    metadata = asset_metadata.get(symbol, {})
    return bool(tokens.intersection(config.qdii_markers)) or bool(metadata.get("is_qdii"))


def _is_commodity_resource(
    symbol: str,
    asset_metadata: MetadataMap,
    config: EtfRiskRuleConfig,
) -> bool:
    tokens = _metadata_tokens(symbol, asset_metadata)
    return bool(tokens.intersection(config.commodity_resource_markers))


def _metadata_tokens(symbol: str, asset_metadata: MetadataMap) -> set:
    metadata = asset_metadata.get(symbol, {})
    tokens = {symbol.lower()}

    for key in ("category", "bucket", "asset_class", "type", "market", "region"):
        value = metadata.get(key)
        if value:
            tokens.add(str(value).strip().lower())

    tags = metadata.get("tags", ())
    if isinstance(tags, str):
        tokens.add(tags.strip().lower())
    elif isinstance(tags, Iterable):
        tokens.update(str(tag).strip().lower() for tag in tags if tag)

    for flag_name, token in (
        ("is_cash", "cash"),
        ("is_qdii", "qdii"),
        ("is_commodity", "commodity"),
        ("is_resource", "resource"),
    ):
        if metadata.get(flag_name):
            tokens.add(token)

    return {token for token in tokens if token}


def _as_optional_fraction(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return _as_fraction(value)


def _as_fraction(value: float) -> float:
    """Coerce a fraction or whole-percent value to a fraction.

    Accepts values in ``[-1.0, 1.0]`` as fractions and values in
    ``(1, 100]`` (or ``[-100, -1)``) as whole percents. Anything outside
    that union raises ``ValueError`` so a mis-units bug fails loudly
    instead of being silently rescaled.
    """

    number = float(value)
    if number != number:  # NaN guard
        raise ValueError(f"Risk-rule weight/percent input is NaN: {value!r}")

    magnitude = abs(number)
    if magnitude <= 1.0 + EPSILON:
        return number
    if magnitude <= 100.0 + EPSILON:
        return number / 100.0
    raise ValueError(
        f"Risk-rule input {value!r} is ambiguous: fractions must be in "
        "[-1, 1] and whole percents in (1, 100]."
    )


def _drop_dust(weights: dict[str, float]) -> None:
    for symbol in list(weights):
        if abs(weights[symbol]) < EPSILON:
            weights[symbol] = 0.0
