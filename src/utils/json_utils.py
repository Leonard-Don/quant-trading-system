"""
JSON序列化工具
"""

import json
import numpy as np
import pandas as pd
from datetime import datetime, date
from typing import Any


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
        elif isinstance(obj, (datetime, date)):
            return obj.isoformat()
        elif isinstance(obj, pd.Timestamp):
            return obj.isoformat()
        elif pd.isna(obj):
            return None
        return super().default(obj)


def safe_json_dumps(data: Any, **kwargs) -> str:
    """安全的JSON序列化，处理NaN和特殊数据类型"""
    return json.dumps(data, cls=CustomJSONEncoder, **kwargs)


def clean_data_for_json(data: Any) -> Any:
    """清理数据以便JSON序列化"""
    if isinstance(data, dict):
        return {k: clean_data_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_data_for_json(item) for item in data]
    elif isinstance(data, pd.DataFrame):
        # 替换NaN值并转换为字典
        return data.fillna(0).to_dict("records")
    elif isinstance(data, pd.Series):
        return data.fillna(0).tolist()
    elif pd.isna(data):
        return None
    elif isinstance(data, (np.integer, np.floating)):
        if np.isnan(data) or np.isinf(data):
            return None
        return float(data) if isinstance(data, np.floating) else int(data)
    elif isinstance(data, np.ndarray):
        return data.tolist()
    else:
        return data
