"""FeatureSet + FeatureSpec: declarative feature definitions for the research pipeline.

A ``FeatureSpec`` pairs a feature name with a pure function ``fn(NormalizedFrame) -> Series``.
A ``FeatureSet`` holds an ordered, deduplicated list of specs. Computation is
deterministic: features are evaluated in declared order, the output DataFrame's
column order matches that, and the index is taken from the input frame.

Tiny on purpose — the heavy lifting is in user-supplied feature functions. Common
quant features (returns, rolling means) can be expressed in two lines using pandas.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

import pandas as pd

from .normalized_frame import NormalizedFrame

FeatureFn = Callable[[NormalizedFrame], pd.Series]


@dataclass(frozen=True)
class FeatureSpec:
    """A single named feature.

    ``fn`` receives the full ``NormalizedFrame`` (not just one column) so features
    that combine OHLC can be expressed naturally — e.g. ``high - low`` for daily
    range, or ``close.pct_change()`` for next-day return.
    """

    name: str
    fn: FeatureFn

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("FeatureSpec.name must be a non-empty string")
        if not callable(self.fn):
            raise ValueError("FeatureSpec.fn must be callable")


@dataclass(frozen=True)
class FeatureSet:
    """An ordered set of ``FeatureSpec`` evaluated together.

    Duplicate names raise ``ValueError`` at construction so registries can't end up
    with two definitions for the same feature key.
    """

    specs: tuple[FeatureSpec, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        specs = tuple(self.specs)
        names = [s.name for s in specs]
        if len(set(names)) != len(names):
            seen, dupes = set(), []
            for n in names:
                if n in seen:
                    dupes.append(n)
                seen.add(n)
            raise ValueError(f"duplicate feature names: {sorted(set(dupes))}")
        object.__setattr__(self, "specs", specs)

    @classmethod
    def of(cls, specs: Iterable[FeatureSpec]) -> FeatureSet:
        return cls(specs=tuple(specs))

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(s.name for s in self.specs)

    def compute(self, frame: NormalizedFrame) -> pd.DataFrame:
        """Evaluate every spec against ``frame`` and assemble a feature matrix.

        Output:

        * Columns are the spec names in declared order.
        * Index matches ``frame.data.index``.
        * Each function's return is coerced to a Series aligned to the frame index;
          mismatched lengths raise ``ValueError`` so silent broadcasts can't hide
          bugs in feature code.
        """
        if not isinstance(frame, NormalizedFrame):
            raise TypeError("FeatureSet.compute requires a NormalizedFrame")
        index = frame.data.index
        out = pd.DataFrame(index=index)
        for spec in self.specs:
            series = spec.fn(frame)
            if not isinstance(series, pd.Series):
                raise TypeError(
                    f"feature '{spec.name}' did not return a pandas Series "
                    f"(got {type(series).__name__})"
                )
            if len(series) != len(index):
                raise ValueError(
                    f"feature '{spec.name}' length {len(series)} does not match "
                    f"frame index length {len(index)}"
                )
            out[spec.name] = series.values  # align by position; index already shared
        return out


__all__: Sequence[str] = (
    "FeatureFn",
    "FeatureSet",
    "FeatureSpec",
)
