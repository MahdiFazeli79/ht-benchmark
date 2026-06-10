"""htbench — enforcement machinery for the dual-abstraction HT benchmark.

Public surface: handles (identity contract), extract (reference RTL extractor),
resolve (handle<->index + neighborhood), hw2vec_compat (downstream view + R9
guard), validate (rules R1-R9), roundtrip (the gate).

Heavy deps (torch, pyverilog) are imported lazily inside the functions that need
them, so importing the package for pure schema/validate work stays light.
"""

__version__ = "0.1.0"
