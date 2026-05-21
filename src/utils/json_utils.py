"""
JSON序列化工具
"""

import json
import math
from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd


class CustomJSONEncoder(json.JSONEncoder):
    """自定义JSON编码器，处理特殊数据类型"""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (datetime, date)) or isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        elif pd.isna(obj):
            return None
        return super().default(obj)


def safe_json_dumps(data: Any, **kwargs) -> str:
    """安全的JSON序列化，处理NaN和特殊数据类型"""
    # Pre-clean so native Python NaN/Infinity become null instead of leaking
    # through json.dumps as the non-standard NaN/Infinity tokens. Enforce
    # allow_nan=False as a backstop in case a caller bypasses pre-cleaning.
    kwargs.setdefault("allow_nan", False)
    return json.dumps(clean_data_for_json(data), cls=CustomJSONEncoder, **kwargs)


def clean_data_for_json(data: Any) -> Any:
    """清理数据以便JSON序列化"""
    if isinstance(data, dict):
        return {k: clean_data_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_data_for_json(item) for item in data]
    elif isinstance(data, pd.DataFrame):
        # 替换NaN值并转换为字典；recurse so non-finite values (e.g. Inf,
        # which fillna does not replace) are also sanitised.
        return [
            clean_data_for_json(record) for record in data.fillna(0).to_dict("records")
        ]
    elif isinstance(data, pd.Series):
        return [clean_data_for_json(item) for item in data.fillna(0).tolist()]
    elif isinstance(data, (np.integer, np.floating)):
        if np.isnan(data) or np.isinf(data):
            return None
        return float(data) if isinstance(data, np.floating) else int(data)
    elif isinstance(data, float):
        # Native Python float — pd.isna catches NaN but not +/-Infinity,
        # so check explicitly to keep parity with the numpy branch above.
        if not math.isfinite(data):
            return None
        return data
    elif isinstance(data, np.ndarray):
        # Check ndarray before pd.isna(data): pandas returns an array of bools
        # whose truth value is ambiguous. Recurse so Inf/NaN elements become
        # JSON null instead of leaking through nested lists.
        return clean_data_for_json(data.tolist())
    elif pd.isna(data):
        return None
    else:
        return data
