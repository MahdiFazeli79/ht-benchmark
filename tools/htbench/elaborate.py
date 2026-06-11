"""Yosys-elaboration RTL front-end (Phase-1 decision 2026-06-10; spike 65d7513).

Pre-extraction stage that turns a parameterized and/or SystemVerilog production
core into the flat Verilog-2005 that `htbench.extract.extract_rtl` expects, while
preserving the intrinsic (AST-derived) signal handles the labels reference.

Pipeline (validated by the mini-spike, docs/phase1_sv2v_canary.md):

    source(.sv?) --sv2v--> Verilog-2005
                 --yosys--> read_verilog -sv
                            hierarchy -top <top> [-chparam K V ...]
                            proc; flatten; opt_clean
                            write_verilog -noattr
                 --attr-strip--> clean Verilog-2005
                 --> htbench.extract.extract_rtl

Why a separate stage and not raw Pyverilog: Pyverilog parses Verilog-2005 but
cannot ELABORATE packed-parameter generate-if gating (the CVA6-style `CFG[...]`
wall). Yosys `hierarchy -chparam` resolves the generate; `write_verilog` runs
BEFORE techmap so user signal names survive (unlike a gate-level netlist, which
gensyms everything). Yosys does introduce a few deterministic synthetic
intermediate nets (`_N_`); v1 policy is to REPORT them, never reject — they are
not source-intrinsic but a manifest signal never maps to one, and they pass the
forbidden-key check (`is_synthetic_net` / `partition_synthetic` here).

The front-end is fail-loud: any sv2v or Yosys error raises `ElaborationError`.
It never silently falls back to raw Pyverilog — that would reintroduce the exact
elaboration wall this stage exists to close (the project's no-silent-failure
stance, same as the forbidden-key validator and the secret scanner).

Provenance: `ElaborationResult.provenance()` is a reproducibility record (chparams,
tool versions, yosys script). It is NOT yet part of the frozen metadata schema
(metadata.schema.json is additionalProperties:false); folding it in is the
proposed spec round 8. Until then it is written as an `elaboration.json` sidecar.
"""

from __future__ import annotations

import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

# Yosys `write_verilog -noattr` already drops `(* ... *)`, but sv2v can emit
# synthesis attributes (`(* full_case, parallel_case *)`) on other paths; this
# defensive strip is the shim the sv2v canary identified. Usually a no-op here.
_ATTR_RE = re.compile(r"\(\*.*?\*\)", re.DOTALL)

# Tool-generated (non-source-intrinsic) handle shapes. None correspond to a
# manifest-inserted signal; all are deterministic within pinned tools. Widened
# after the CVA6 canary (docs/phase1_sv2v_canary.md) surfaced sv2v temporaries
# and inlined-function artifacts that the toy fixture never produced:
#   - `_N_`        : Yosys proc/flatten intermediate nets (`top._0_`)
#   - `_sv2v_N`    : sv2v lowering temporaries (`top.\i_mul._sv2v_0`)
#   - `$`          : sv2v/yosys inlined-function & gensym symbols
#                    (`...sext32to64$func$mul_flat.v:111$81.operand`)
_SYNTHETIC_PATTERNS = (
    re.compile(r"(?:^|\.)_\d+_$"),
    re.compile(r"(?:^|\.)_sv2v_\d+$"),
    re.compile(r"\$"),
)


class ElaborationError(RuntimeError):
    """sv2v or Yosys failed. Raised loud with captured stderr; the front-end
    never silently degrades to raw Pyverilog."""


# --------------------------------------------------------------------------- #
# Detection helpers
# --------------------------------------------------------------------------- #

def is_systemverilog(paths, override: bool | None = None) -> bool:
    """Whether sources need sv2v. `override` wins; otherwise any `.sv`/`.svh`."""
    if override is not None:
        return override
    return any(str(p).endswith((".sv", ".svh")) for p in paths)


def is_synthetic_net(handle: str) -> bool:
    """True if `handle` names a Yosys-introduced intermediate net (`_N_`).

    Synthetic handles are valid (not forbidden), but they are not source-intrinsic
    and a manifest-inserted signal never maps to one. Covers Yosys `_N_` nets,
    sv2v `_sv2v_N` temporaries, and `$`-bearing inlined-function artifacts.
    """
    base = handle.split("[", 1)[0]            # ignore an optional bit-select
    return any(p.search(base) for p in _SYNTHETIC_PATTERNS)


def partition_synthetic(handles):
    """Split `handles` into (intrinsic, synthetic), order preserved."""
    intrinsic = [h for h in handles if not is_synthetic_net(h)]
    synthetic = [h for h in handles if is_synthetic_net(h)]
    return intrinsic, synthetic


# --------------------------------------------------------------------------- #
# Elaboration
# --------------------------------------------------------------------------- #

@dataclass
class ElaborationResult:
    verilog_path: str          # clean Verilog-2005, ready for extract_rtl
    top: str
    chparams: dict             # parameter -> value used for this elaboration
    sv2v_used: bool
    yosys_script: str
    tool_versions: dict
    work_dir: str

    def provenance(self) -> dict:
        """Reproducibility record (sidecar `elaboration.json`; round-8 candidate
        for metadata.json)."""
        return {
            "stage": "yosys_elaborate",
            "top": self.top,
            "chparams": dict(self.chparams),
            "sv2v_used": self.sv2v_used,
            "yosys_script": self.yosys_script,
            "tool_versions": dict(self.tool_versions),
        }


def _run(cmd) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise ElaborationError(f"tool not found: {cmd[0]} ({e})") from e
    if p.returncode != 0:
        raise ElaborationError(
            f"{cmd[0]} failed (exit {p.returncode}):\n{p.stderr.strip()[:2000]}"
        )
    return p.stdout


def _chparam_args(chparams: dict) -> list[str]:
    args: list[str] = []
    for k in sorted(chparams):                # deterministic order
        args += ["-chparam", str(k), str(chparams[k])]
    return args


def elaborate(
    sources,
    top: str,
    chparams: dict | None = None,
    *,
    systemverilog: bool | None = None,
    work_dir: str | None = None,
    yosys_bin: str = "yosys",
    sv2v_bin: str = "sv2v",
) -> ElaborationResult:
    """Elaborate `sources` into flat Verilog-2005 with intrinsic names intact.

    `chparams` pins a concrete configuration (one config = one sample, per the
    config-selection policy). `systemverilog` forces/skips sv2v; default is
    inferred from file extensions.
    """
    if isinstance(sources, (str, Path)):
        sources = [sources]
    sources = [str(s) for s in sources]
    chparams = dict(chparams or {})
    sv = is_systemverilog(sources, systemverilog)
    wd = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="htbench_elab_"))
    wd.mkdir(parents=True, exist_ok=True)

    tool_versions = {"yosys": _run([yosys_bin, "-V"]).strip()}

    # Stage 1 — SystemVerilog -> Verilog-2005 via sv2v (only when needed).
    if sv:
        tool_versions["sv2v"] = _run([sv2v_bin, "--version"]).strip()
        v2005 = wd / "sv2v_out.v"
        v2005.write_text(_run([sv2v_bin, *sources]))
        yosys_inputs = [str(v2005)]
    else:
        yosys_inputs = sources

    # Stage 2 — Yosys: resolve params/generates, flatten, re-emit RTL.
    elaborated = wd / "elaborated.v"
    read_cmds = "; ".join(f"read_verilog -sv {p}" for p in yosys_inputs)
    chparam = " ".join(_chparam_args(chparams))
    hierarchy = f"hierarchy -top {top}" + (f" {chparam}" if chparam else "")
    script = (
        f"{read_cmds}; {hierarchy}; proc; flatten; opt_clean; "
        f"write_verilog -noattr {elaborated}"
    )
    _run([yosys_bin, "-q", "-p", script])
    if not elaborated.exists():
        raise ElaborationError("yosys produced no output netlist")

    # Stage 3 — defensive attribute strip (the sv2v-canary shim).
    text = elaborated.read_text()
    stripped = _ATTR_RE.sub("", text)
    if stripped != text:
        elaborated.write_text(stripped)

    return ElaborationResult(
        verilog_path=str(elaborated),
        top=top,
        chparams=chparams,
        sv2v_used=sv,
        yosys_script=script,
        tool_versions=tool_versions,
        work_dir=str(wd),
    )


def metadata_block(result: "ElaborationResult", graph: dict | None = None) -> dict:
    """Build the optional `metadata.json` `elaboration` block (spec round 8).

    `graph` (if given) is the extracted DFG, used to count synthetic `_N_` nets.
    The returned dict conforms to metadata.schema.json's `elaboration` property.
    """
    tv = result.tool_versions
    synthetic = 0
    if graph is not None:
        _, synth = partition_synthetic([n["handle"] for n in graph["nodes"]])
        synthetic = len(synth)
    return {
        "front_end": "yosys_elaborate",
        "sv2v_used": result.sv2v_used,
        "sv2v_version": tv.get("sv2v"),
        "yosys_version": tv.get("yosys"),
        "top_module": result.top,
        "chparams": {k: str(v) for k, v in result.chparams.items()},
        "synthetic_nets": synthetic,
    }


def elaborate_and_extract(sources, top: str, chparams: dict | None = None, **kw):
    """Elaborate then run the reference RTL extractor.

    Returns ``(graph_dict, ElaborationResult)``. `graph_dict` conforms to
    graph.schema.json (graph_kind == "dfg_rtl").
    """
    from . import extract
    passthrough = {k: v for k, v in kw.items()
                   if k in ("systemverilog", "work_dir", "yosys_bin", "sv2v_bin")}
    res = elaborate(sources, top, chparams=chparams, **passthrough)
    g = extract.extract_rtl(res.verilog_path, top=top)
    return g, res


# --------------------------------------------------------------------------- #
# Config-selection policy (Phase-1 decision 2026-06-10)
# --------------------------------------------------------------------------- #

@dataclass
class VariantPlan:
    """One elaboration target: a (variant_group, chparams) pair -> one sample.

    `leakage_linked` is True when more than one config of the SAME parameterized
    design is sourced; all such variants share one `variant_group` so split
    atomicity (spec §8) keeps them on the same side of any train/test split.
    """
    variant_group: str
    sample_id: str
    chparams: dict
    leakage_linked: bool


def _config_key(chparams: dict) -> str:
    if not chparams:
        return "default"
    return "-".join(f"{k}{chparams[k]}" for k in sorted(chparams))


def plan_variants(variant_group: str, configs, *, sample_id_base: str | None = None):
    """Config-selection policy.

    One concrete config = one sample. Multiple configs of the same parameterized
    design = leakage-linked variants sharing ONE `variant_group`. Returns a list
    of `VariantPlan`, deterministic in input order, with `sample_id` derived from
    the config so it is stable and self-describing.
    """
    configs = list(configs)
    if not configs:
        raise ValueError("plan_variants requires at least one config")
    base = sample_id_base or variant_group
    linked = len(configs) > 1
    plans: list[VariantPlan] = []
    seen: set[str] = set()
    for cfg in configs:
        cfg = dict(cfg or {})
        sid = f"{base}__{_config_key(cfg)}"
        if sid in seen:
            raise ValueError(f"duplicate config produces duplicate sample_id: {sid}")
        seen.add(sid)
        plans.append(VariantPlan(variant_group, sid, cfg, linked))
    return plans
