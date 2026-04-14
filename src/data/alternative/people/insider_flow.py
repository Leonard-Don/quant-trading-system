"""Curated insider flow signals for people-layer pricing analysis."""

from __future__ import annotations

from typing import Any, Dict


INSIDER_FLOW_CATALOG: Dict[str, Dict[str, Any]] = {
    "NVDA": {"net_action": "selling", "net_value_musd": -220.0, "transaction_count": 6, "confidence": 0.63},
    "AAPL": {"net_action": "selling", "net_value_musd": -95.0, "transaction_count": 4, "confidence": 0.58},
    "MSFT": {"net_action": "neutral", "net_value_musd": -8.0, "transaction_count": 2, "confidence": 0.56},
    "META": {"net_action": "selling", "net_value_musd": -140.0, "transaction_count": 5, "confidence": 0.61},
    "GOOGL": {"net_action": "mixed", "net_value_musd": -22.0, "transaction_count": 4, "confidence": 0.55},
    "AMZN": {"net_action": "mixed", "net_value_musd": -18.0, "transaction_count": 3, "confidence": 0.54},
    "TSLA": {"net_action": "selling", "net_value_musd": -180.0, "transaction_count": 5, "confidence": 0.66},
    "BABA": {"net_action": "neutral", "net_value_musd": 0.0, "transaction_count": 1, "confidence": 0.45},
    "BIDU": {"net_action": "mixed", "net_value_musd": -12.0, "transaction_count": 2, "confidence": 0.44},
    "TSM": {"net_action": "buying", "net_value_musd": 24.0, "transaction_count": 2, "confidence": 0.52},
}


ACTION_SIGNAL = {
    "buying": 0.35,
    "selling": -0.35,
    "mixed": -0.08,
    "neutral": 0.0,
}


class InsiderFlowProvider:
    """Return a lightweight insider-flow view for a symbol."""

    def get_signal(self, symbol: str, company_name: str = "") -> Dict[str, Any]:
        normalized_symbol = str(symbol or "").strip().upper()
        item = dict(
            INSIDER_FLOW_CATALOG.get(normalized_symbol)
            or {"net_action": "neutral", "net_value_musd": 0.0, "transaction_count": 0, "confidence": 0.3}
        )

        net_action = item["net_action"]
        action_score = ACTION_SIGNAL.get(net_action, 0.0)
        magnitude = min(abs(float(item.get("net_value_musd", 0.0))) / 250.0, 1.0)
        conviction_score = round(action_score * (0.6 + magnitude * 0.4), 2)

        if conviction_score >= 0.18:
            label = "内部人增持偏积极"
        elif conviction_score <= -0.18:
            label = "内部人减持偏谨慎"
        else:
            label = "内部人交易信号中性"

        return {
            "symbol": normalized_symbol,
            "company_name": company_name or normalized_symbol,
            "net_action": net_action,
            "transaction_count": int(item.get("transaction_count", 0)),
            "net_value_musd": round(float(item.get("net_value_musd", 0.0)), 1),
            "conviction_score": conviction_score,
            "label": label,
            "confidence": round(float(item.get("confidence", 0.3)), 2),
            "source": "curated_insider_flows",
            "summary": f"{company_name or normalized_symbol} 近端内部人交易呈 {net_action}，净额 {float(item.get('net_value_musd', 0.0)):.1f}M 美元。",
        }
