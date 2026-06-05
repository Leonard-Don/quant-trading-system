"""Cohesive sibling modules backing :mod:`src.backtest.strategy_statistical_tests`.

The public API lives at ``src.backtest.strategy_statistical_tests`` (unchanged
import path). This package holds the implementation split into focused modules:

* :mod:`.results` — frozen result dataclasses.
* :mod:`.core` — loss functions, HAC variance, alignment helpers, and the
  three orthogonal pairwise tests (DM, block bootstrap, Sharpe difference).
* :mod:`.corrections` — Bonferroni / Holm multiple-testing corrections.
* :mod:`.power` — Minimum Detectable Effect inversion and forward power.
* :mod:`.reporting` — DataFrame helpers and the walk-forward pipeline.
"""

from __future__ import annotations
