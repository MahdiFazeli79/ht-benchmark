"""R9 collision-rate measurement (task #27 — the instrument).

`hw2vec_compat.assert_injective` rejects a single sample on its FIRST R9
collision (HW2VEC's name mangle aliasing two distinct AST handles). Before the
corpus is sourced we need the *rate* at which that mangle collides on REALISTIC
RTL — bus bits, generate-block instances, deep hierarchical flattening — because
if it is high (memory flags >20–30% as a finding) the handle function or a
normalization step must change BEFORE 500 designs are built, not after. The cost
of learning a bad rate now is ~20 circuits of rework; after sourcing it is 500.

This module is the instrument. The pure measurement (`collisions_in`,
`measure_graph`, `measure_graphs`) runs on already-extracted graphs and is fully
testable offline. The `measure_design_specs` driver runs the full
elaborate → extract → measure chain on real designs; pointing it at large
production cores needs a clone (the download boundary — gated). It is wired and
smoke-tested on the elaborate fixture so it is ready to run the moment a corpus
batch is approved.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .hw2vec_compat import hw2vec_name_transform

# Memory-recorded threshold: above this design-collision rate on realistic IP,
# the "HW2VEC as downstream view" decision needs revisiting before scaling.
FINDING_THRESHOLD = 0.20


def collisions_in(handles):
    """Group handles by their HW2VEC name transform; return the groups that
    alias two or more DISTINCT handles. Each entry is ``(transformed, [handles])``.

    expr/const handles are not name-mangled (the transform returns them
    unchanged), so they only ever collide with an identical handle — i.e. never
    contribute a real R9 collision.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for h in handles:
        groups[hw2vec_name_transform(h)].append(h)
    out = []
    for transformed, hs in groups.items():
        distinct = sorted(set(hs))
        if len(distinct) > 1:
            out.append((transformed, distinct))
    return sorted(out)


@dataclass
class DesignR9:
    design_id: str
    n_handles: int
    n_named: int                       # named-signal handles (the manglable ones)
    collisions: list                   # [(transformed, [handles...]), ...]
    error: str | None = None           # set if elaborate/extract failed

    @property
    def has_collision(self) -> bool:
        return bool(self.collisions)

    @property
    def n_colliding_handles(self) -> int:
        return sum(len(hs) for _, hs in self.collisions)


@dataclass
class R9RateReport:
    designs: list = field(default_factory=list)

    @property
    def measured(self):
        return [d for d in self.designs if d.error is None]

    @property
    def n_measured(self) -> int:
        return len(self.measured)

    @property
    def n_failed(self) -> int:
        return sum(1 for d in self.designs if d.error is not None)

    @property
    def n_with_collision(self) -> int:
        return sum(1 for d in self.measured if d.has_collision)

    @property
    def design_collision_rate(self) -> float:
        return self.n_with_collision / self.n_measured if self.n_measured else 0.0

    def render(self) -> str:
        L = ["# R9 collision-rate report\n"]
        rate = self.design_collision_rate
        verdict = ("FINDING — revisit HW2VEC-as-view / handle function"
                   if rate >= FINDING_THRESHOLD else "within tolerance")
        L.append(f"- designs measured: {self.n_measured}  (failed: {self.n_failed})")
        L.append(f"- designs with ≥1 R9 collision: {self.n_with_collision}")
        L.append(f"- **design collision rate: {rate:.0%}** "
                 f"(threshold {FINDING_THRESHOLD:.0%}) → {verdict}\n")
        offenders = sorted((d for d in self.measured if d.has_collision),
                           key=lambda d: d.n_colliding_handles, reverse=True)
        if offenders:
            L.append("## Colliding designs\n")
            for d in offenders:
                L.append(f"- `{d.design_id}`: {len(d.collisions)} colliding group(s), "
                         f"{d.n_colliding_handles} handles")
                for transformed, hs in d.collisions[:3]:
                    L.append(f"    - {hs} → `{transformed}`")
        if self.n_failed:
            L.append("\n## Failed (elaborate/extract error)\n")
            for d in self.designs:
                if d.error is not None:
                    L.append(f"- `{d.design_id}`: {d.error}")
        return "\n".join(L)


def measure_graph(design_id: str, graph: dict) -> DesignR9:
    """Measure R9 collisions in one extracted graph."""
    handles = [n["handle"] for n in graph["nodes"]]
    named = [h for h in handles if not h.startswith(("expr:", "const:"))]
    return DesignR9(design_id, len(handles), len(named), collisions_in(handles))


def measure_graphs(named_graphs) -> R9RateReport:
    """Aggregate R9 measurement over many extracted graphs.

    `named_graphs` is a dict ``{design_id: graph}`` or an iterable of
    ``(design_id, graph)``.
    """
    items = named_graphs.items() if isinstance(named_graphs, dict) else named_graphs
    return R9RateReport([measure_graph(i, g) for i, g in items])


def measure_design_specs(specs) -> R9RateReport:
    """Full chain: elaborate -> extract -> measure, over real design specs.

    Each spec: ``{"design_id", "sources", "top", "chparams"?, "systemverilog"?}``.
    A design that fails to elaborate/extract is recorded with its error and does
    not abort the run (fail-loud per design, continue the aggregate). Running
    this on production cores needs the sources present locally (post-clone).
    """
    from . import elaborate as E

    designs = []
    for spec in specs:
        did = spec["design_id"]
        try:
            g, _ = E.elaborate_and_extract(
                spec["sources"], spec["top"],
                chparams=spec.get("chparams"),
                systemverilog=spec.get("systemverilog"),
            )
            designs.append(measure_graph(did, g))
        except Exception as e:  # noqa: BLE001 — per-design isolation, recorded
            designs.append(DesignR9(did, 0, 0, [], error=f"{type(e).__name__}: {e}"))
    return R9RateReport(designs)
