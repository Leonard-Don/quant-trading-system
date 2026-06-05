"""Internal submodules for :mod:`src.data.providers.sina_ths_adapter`.

This package holds cohesive, behavior-preserving extractions of the
``SinaIndustryAdapter`` internals (industry-name mapping tables and pure
parsing/normalization leaf helpers). The public adapter class continues to live
in ``src.data.providers.sina_ths_adapter`` and re-exports everything it needs
from here, so the public import path and API are unchanged.
"""
