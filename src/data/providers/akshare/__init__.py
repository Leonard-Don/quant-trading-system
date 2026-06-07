"""Internal submodules for :mod:`src.data.providers.akshare_provider`.

This package holds cohesive, behavior-preserving extractions of the
``AKShareProvider`` internals (the 申万 industry-code mapping table, AKShare
column-rename maps, and pure parsing/normalization leaf helpers). The public
provider class continues to live in ``src.data.providers.akshare_provider`` and
re-exports / re-binds everything it needs from here, so the public import path
and API are unchanged.
"""
