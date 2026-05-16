"""Regression tests for src.utils.json_utils.

These guard the invariant that ``safe_json_dumps`` produces strictly valid
JSON (no ``NaN``/``Infinity`` tokens) and that ``clean_data_for_json``
sanitises non-finite scalars uniformly across native Python and numpy
float types.
"""

import json

import numpy as np
import pandas as pd
import pytest

from src.utils.json_utils import clean_data_for_json, safe_json_dumps


class TestSafeJsonDumpsProducesValidJson:
    """``safe_json_dumps`` must never emit NaN/Infinity tokens."""

    def test_python_float_nan_serializes_to_null(self):
        out = safe_json_dumps(float("nan"))
        assert json.loads(out) is None

    def test_python_float_inf_serializes_to_null(self):
        out = safe_json_dumps(float("inf"))
        assert json.loads(out) is None

    def test_python_float_negative_inf_serializes_to_null(self):
        out = safe_json_dumps(float("-inf"))
        assert json.loads(out) is None

    def test_numpy_float_nan_serializes_to_null(self):
        out = safe_json_dumps(np.float64("nan"))
        assert json.loads(out) is None

    def test_numpy_float_inf_serializes_to_null(self):
        out = safe_json_dumps(np.float64("inf"))
        assert json.loads(out) is None

    def test_list_with_inf_produces_valid_json(self):
        out = safe_json_dumps([1.0, float("inf"), 2.0])
        assert json.loads(out) == [1.0, None, 2.0]

    def test_dict_with_nan_and_inf_produces_valid_json(self):
        out = safe_json_dumps({"a": float("nan"), "b": float("inf"), "c": 1.5})
        assert json.loads(out) == {"a": None, "b": None, "c": 1.5}

    def test_nested_structure_produces_valid_json(self):
        payload = {"rows": [{"x": float("inf")}, {"x": 2.0}]}
        out = safe_json_dumps(payload)
        assert json.loads(out) == {"rows": [{"x": None}, {"x": 2.0}]}


class TestSafeJsonDumpsPreservesFiniteValues:
    """Finite numerics, including explicit zero and False, must round-trip."""

    def test_explicit_zero_float_preserved(self):
        assert json.loads(safe_json_dumps(0.0)) == 0.0

    def test_explicit_zero_int_preserved(self):
        assert json.loads(safe_json_dumps(0)) == 0

    def test_explicit_false_preserved(self):
        assert json.loads(safe_json_dumps(False)) is False

    def test_finite_float_preserved(self):
        assert json.loads(safe_json_dumps(3.14)) == 3.14

    def test_none_preserved(self):
        assert json.loads(safe_json_dumps(None)) is None


class TestCleanDataForJsonNonFinite:
    """``clean_data_for_json`` maps every non-finite scalar to ``None``."""

    @pytest.mark.parametrize(
        "value",
        [
            float("nan"),
            float("inf"),
            float("-inf"),
            np.float64("nan"),
            np.float64("inf"),
            np.float64("-inf"),
        ],
    )
    def test_non_finite_scalar_becomes_none(self, value):
        assert clean_data_for_json(value) is None

    def test_finite_python_float_preserved(self):
        assert clean_data_for_json(1.5) == 1.5

    def test_explicit_zero_preserved(self):
        assert clean_data_for_json(0.0) == 0.0

    def test_explicit_false_preserved(self):
        assert clean_data_for_json(False) is False

    def test_list_with_mixed_non_finite_cleaned(self):
        result = clean_data_for_json([1.0, float("inf"), float("nan"), 2.0])
        assert result == [1.0, None, None, 2.0]
        # Output must be JSON-serialisable without allow_nan.
        json.dumps(result, allow_nan=False)

    def test_dataframe_records_have_no_non_finite(self):
        df = pd.DataFrame({"x": [1.0, float("inf"), 2.0]})
        result = clean_data_for_json(df)
        # NaN policy is unchanged (fillna(0)); Inf must be sanitised.
        json.dumps(result, allow_nan=False)

    def test_numpy_array_with_non_finite_values_is_cleaned_recursively(self):
        result = clean_data_for_json(np.array([0.0, np.inf, -np.inf, np.nan, 2.5]))
        assert result == [0.0, None, None, None, 2.5]
        json.dumps(result, allow_nan=False)
