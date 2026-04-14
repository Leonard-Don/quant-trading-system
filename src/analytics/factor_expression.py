"""Safe factor expression evaluator for custom quantitative factors."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List

import numpy as np
import pandas as pd


ALLOWED_COLUMNS = {"open", "high", "low", "close", "volume", "adj_close"}
ALLOWED_FUNCTIONS = {
    "rank",
    "zscore",
    "sma",
    "ema",
    "rolling_mean",
    "rolling_std",
    "pct_change",
    "delay",
    "abs",
    "min",
    "max",
    "clip",
    "log",
}


@dataclass
class FactorEvaluationResult:
    expression: str
    latest_value: float | None
    preview: List[Dict[str, Any]]
    diagnostics: Dict[str, Any]


class FactorExpressionError(ValueError):
    """Raised when a factor expression is unsafe or invalid."""


class FactorExpressionEngine:
    """Evaluate a constrained factor expression against OHLCV market data."""

    def evaluate(self, data: pd.DataFrame, expression: str, preview_rows: int = 30) -> FactorEvaluationResult:
        if data is None or data.empty:
            raise FactorExpressionError("data is empty")
        normalized_expression = str(expression or "").strip()
        if not normalized_expression:
            raise FactorExpressionError("expression is required")

        frame = self._normalize_frame(data)
        tree = ast.parse(normalized_expression, mode="eval")
        self._validate(tree)
        context = {column: frame[column] for column in frame.columns if column in ALLOWED_COLUMNS}
        series = self._evaluate_node(tree.body, context)
        series = self._as_series(series, frame.index).replace([np.inf, -np.inf], np.nan)
        latest = series.dropna().iloc[-1] if not series.dropna().empty else None
        preview = pd.DataFrame({"date": frame.index, "factor": series}).tail(max(1, min(preview_rows, 200)))
        return FactorEvaluationResult(
            expression=normalized_expression,
            latest_value=None if latest is None or pd.isna(latest) else float(latest),
            preview=[
                {
                    "date": pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
                    "factor": None if pd.isna(row["factor"]) else round(float(row["factor"]), 6),
                }
                for _, row in preview.iterrows()
            ],
            diagnostics={
                "rows": int(len(frame)),
                "non_null_factor_points": int(series.notna().sum()),
                "columns": [column for column in frame.columns if column in ALLOWED_COLUMNS],
            },
        )

    def _normalize_frame(self, data: pd.DataFrame) -> pd.DataFrame:
        frame = data.copy()
        frame.columns = [str(column).lower() for column in frame.columns]
        if "adj close" in frame.columns and "adj_close" not in frame.columns:
            frame["adj_close"] = frame["adj close"]
        if "close" not in frame.columns and "adj_close" in frame.columns:
            frame["close"] = frame["adj_close"]
        missing = {"close"} - set(frame.columns)
        if missing:
            raise FactorExpressionError("data must include close price")
        for column in ALLOWED_COLUMNS:
            if column in frame.columns:
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
        return frame.sort_index()

    def _validate(self, tree: ast.AST) -> None:
        allowed_nodes = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Call,
            ast.Name,
            ast.Load,
            ast.Constant,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.Pow,
            ast.Mod,
            ast.USub,
            ast.UAdd,
        )
        for node in ast.walk(tree):
            if not isinstance(node, allowed_nodes):
                raise FactorExpressionError(f"unsupported syntax: {node.__class__.__name__}")
            if isinstance(node, ast.Name) and node.id not in ALLOWED_COLUMNS and node.id not in ALLOWED_FUNCTIONS:
                raise FactorExpressionError(f"unknown name: {node.id}")
            if isinstance(node, ast.Call):
                if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCTIONS:
                    raise FactorExpressionError("only whitelisted factor functions are allowed")
                if node.keywords:
                    raise FactorExpressionError("keyword arguments are not supported")

    def _evaluate_node(self, node: ast.AST, context: Dict[str, pd.Series]) -> Any:
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise FactorExpressionError("only numeric constants are supported")
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id not in context:
                raise FactorExpressionError(f"column is unavailable: {node.id}")
            return context[node.id]
        if isinstance(node, ast.UnaryOp):
            operand = self._evaluate_node(node.operand, context)
            return -operand if isinstance(node.op, ast.USub) else operand
        if isinstance(node, ast.BinOp):
            left = self._evaluate_node(node.left, context)
            right = self._evaluate_node(node.right, context)
            return self._apply_operator(node.op, left, right)
        if isinstance(node, ast.Call):
            args = [self._evaluate_node(arg, context) for arg in node.args]
            return self._apply_function(node.func.id, args, context)
        raise FactorExpressionError(f"unsupported expression node: {node.__class__.__name__}")

    def _apply_operator(self, operator: ast.operator, left: Any, right: Any) -> Any:
        if isinstance(operator, ast.Add):
            return left + right
        if isinstance(operator, ast.Sub):
            return left - right
        if isinstance(operator, ast.Mult):
            return left * right
        if isinstance(operator, ast.Div):
            return left / right
        if isinstance(operator, ast.Pow):
            return left ** right
        if isinstance(operator, ast.Mod):
            return left % right
        raise FactorExpressionError("operator is not supported")

    def _apply_function(self, name: str, args: List[Any], context: Dict[str, pd.Series]) -> Any:
        if name == "rank":
            return self._as_series(args[0], next(iter(context.values())).index).rank(pct=True)
        if name == "zscore":
            series = self._as_series(args[0], next(iter(context.values())).index)
            std = series.std(ddof=0)
            return (series - series.mean()) / std if std else series * 0
        if name in {"sma", "rolling_mean"}:
            series, window = self._series_window(args)
            return series.rolling(window=window, min_periods=max(1, window // 3)).mean()
        if name == "rolling_std":
            series, window = self._series_window(args)
            return series.rolling(window=window, min_periods=max(1, window // 3)).std(ddof=0)
        if name == "ema":
            series, window = self._series_window(args)
            return series.ewm(span=window, adjust=False).mean()
        if name == "pct_change":
            series, window = self._series_window(args, default_window=1)
            return series.pct_change(window)
        if name == "delay":
            series, window = self._series_window(args, default_window=1)
            return series.shift(window)
        if name == "abs":
            return abs(args[0])
        if name == "min":
            return self._combine(args, reducer="min", context=context)
        if name == "max":
            return self._combine(args, reducer="max", context=context)
        if name == "clip":
            if len(args) != 3:
                raise FactorExpressionError("clip(series, lower, upper) requires three arguments")
            series = self._as_series(args[0], next(iter(context.values())).index)
            return series.clip(lower=float(args[1]), upper=float(args[2]))
        if name == "log":
            return np.log(args[0])
        raise FactorExpressionError(f"function is not supported: {name}")

    def _series_window(self, args: List[Any], default_window: int | None = None) -> tuple[pd.Series, int]:
        if not args:
            raise FactorExpressionError("function requires a series argument")
        index = args[0].index if isinstance(args[0], pd.Series) else None
        series = self._as_series(args[0], index)
        raw_window = args[1] if len(args) > 1 else default_window
        if raw_window is None:
            raise FactorExpressionError("rolling function requires a window")
        window = max(1, min(int(raw_window), 756))
        return series, window

    def _combine(self, args: Iterable[Any], reducer: str, context: Dict[str, pd.Series]) -> Any:
        values = list(args)
        if len(values) < 2:
            raise FactorExpressionError(f"{reducer} requires at least two arguments")
        index = next(iter(context.values())).index
        frame = pd.concat([self._as_series(value, index) for value in values], axis=1)
        return frame.min(axis=1) if reducer == "min" else frame.max(axis=1)

    def _as_series(self, value: Any, index: Any) -> pd.Series:
        if isinstance(value, pd.Series):
            return value
        if index is None:
            raise FactorExpressionError("scalar cannot be converted without an index")
        return pd.Series(float(value), index=index)


factor_expression_engine = FactorExpressionEngine()
