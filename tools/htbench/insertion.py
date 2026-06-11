"""Phase-2 Trojan-insertion engine — the no-spend spine (plan §2.1-2.4).

Ties together the engine's metered-free parts so the only paid component is a
real LLM client, and even that runs only after the cost guard clears it:

  - `build_prompt`      — structured insertion prompt encoding the taxonomy (§2.1).
  - `LLMClient`/`Mock`  — the model behind an interface; mocks in tests, the paid
                          client is the ONLY metered call.
  - `parse_infected`    — pull the delimited infected RTL out of the response.
  - `ground_truth`      — generation-time ground truth by STRUCTURAL DIFF of clean
                          vs infected (§2.2), never keyword scanning. Reuses the
                          validator's exact diff so the manifest passes R6 by
                          construction.
  - `generate_sample`   — the reject-and-repair loop (§2.4) routed through
                          `CostGuard`: pre_call_check before every call, record
                          spend after, record accept/reject for the yield floor.
                          The verification gauntlet (§2.3) is injected as a
                          callback, so the loop is testable now and the real
                          iverilog/yosys gauntlet plugs in unchanged.

NOTHING here calls a paid API on its own. The prompt CONTENT below is a first
draft to be reviewed before the pilot — the spine is the stable part.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import cost_guard as CG
from . import validate as _V

# The model returns TWO blocks: the full infected module (diffed structurally for
# ground truth) and an activation WITNESS (a checkable "apply X, see Y" claim that
# activation-proof verifies by dual assertion — fires on infected, silent on clean).
_INFECTED_RE = re.compile(r"<INFECTED>\s*(.*?)\s*</INFECTED>", re.DOTALL)
_ACTIVATION_RE = re.compile(r"<ACTIVATION>\s*(.*?)\s*</ACTIVATION>", re.DOTALL)

# Feasibility (spec §10 R1-R3) is enforced at SPEC CONSTRUCTION, never in the
# prompt — the prompt must never be asked for a forbidden taxonomy cell.
_ALWAYS_ON_PAYLOADS = {"leak_information", "degrade_performance"}


# --------------------------------------------------------------------------- #
# LLM client interface (the only place a paid call can happen)
# --------------------------------------------------------------------------- #

@dataclass
class LLMResponse:
    text: str
    in_tokens: int
    out_tokens: int
    model: str


class LLMClient:
    """Interface. A real impl (e.g. Anthropic) is the only metered code and is
    added once the API key is provisioned; it must route through CostGuard."""

    def complete(self, prompt: str) -> LLMResponse:  # pragma: no cover - abstract
        raise NotImplementedError


@dataclass
class MockLLMClient(LLMClient):
    """Deterministic client for tests — returns queued responses, no network.
    Token counts approximate the real tokenizer (≈4 chars/token) so cost-guard
    wiring is exercised without spend."""
    responses: list[str]
    model: str = "claude-sonnet-4"
    _i: int = 0

    def complete(self, prompt: str) -> LLMResponse:
        text = self.responses[min(self._i, len(self.responses) - 1)]
        self._i += 1
        return LLMResponse(text, _approx_tokens(prompt), _approx_tokens(text), self.model)


def _approx_tokens(s: str) -> int:
    return max(1, len(s) // 4)


def load_env(path: str = ".env") -> None:
    """Load KEY=VALUE lines from a .env file into os.environ without overriding
    already-set vars. Minimal, no dependency — so the Anthropic SDK (which reads
    ANTHROPIC_API_KEY from the environment) sees the gitignored key."""
    import os
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


@dataclass
class AnthropicClient(LLMClient):
    """The paid client — the ONLY metered call in the whole engine.

    Lazy SDK import (the module stays importable without `anthropic`); reads the
    key from the environment (`load_env` first). `_client` is injectable so tests
    mock the SDK at zero cost. `model` is REQUIRED — no magic default; the exact
    API model id is set deliberately at pilot time. This client makes the raw
    call only; the cost guard's pre_call_check/record_spend wrap it in
    `generate_sample`, so spend control is never the client's responsibility."""
    model: str
    max_tokens: int = 4096
    temperature: float = 1.0          # pinned, not left to the API default; logged per manifest
    _client: object = None

    def __post_init__(self):
        if self._client is None:
            load_env()
            import anthropic
            self._client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env

    def complete(self, prompt: str) -> LLMResponse:
        resp = self._client.messages.create(
            model=self.model, max_tokens=self.max_tokens, temperature=self.temperature,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(getattr(b, "text", "") for b in resp.content
                       if getattr(b, "type", "") == "text")
        return LLMResponse(text, resp.usage.input_tokens, resp.usage.output_tokens, self.model)


# --------------------------------------------------------------------------- #
# Prompt, parsing, ground truth
# --------------------------------------------------------------------------- #

@dataclass
class InsertionSpec:
    clean_rtl: str
    top_module: str
    activation: str                 # taxonomy axes (Karri/Trust-Hub)
    trigger_source: str | None
    trigger_mechanism: str | None
    payload: str
    target_net: str | None = None

    def __post_init__(self):
        # Feasibility guard (R1-R3) — an infeasible cell can never be constructed,
        # so the prompt is never asked for one (the guard lives here, not the prompt).
        if self.activation == "always_on":
            if self.trigger_source is not None or self.trigger_mechanism is not None:
                raise ValueError("R1: always_on must have null trigger_source/mechanism")
            if self.payload not in _ALWAYS_ON_PAYLOADS:
                raise ValueError(
                    f"R3: always_on payload must be in {sorted(_ALWAYS_ON_PAYLOADS)}")
        elif self.activation == "triggered":
            if self.trigger_source is None or self.trigger_mechanism is None:
                raise ValueError("R2: triggered must have non-null trigger_source/mechanism")
        else:
            raise ValueError(f"activation must be 'always_on' or 'triggered': {self.activation!r}")


# Prompt-construction logic version, recorded in generator.prompt_version so the
# version travels with each sample and v1/v2 corpora coexist. The LOCKED base body
# below is byte-identical to v1; v2 adds ONLY the host-observable repair steering
# (_steer_feedback), which fires on the Trojan-internal-witness failure. So
# prompt_hash (the per-spec base-body hash) is unchanged from v1; prompt_version
# distinguishes the repair policy. Absence of the field on a sample ⇒ the pre-
# versioning v1 locked prompt (the ten first-pilot manifests).
PROMPT_VERSION = "v2"


# Host-observable repair steering (prompt_v2, OUTSIDE the locked base body). A
# witness that keys on Trojan-internal state cannot be replayed against the clean
# module (the gauntlet returns "witness not applicable to clean"); this one
# instruction steers the retry toward state the clean module actually has.
_HOST_OBSERVABLE_STEERING = (
    " To fix this, express the trigger using ONLY signals that exist in the clean "
    "module: its input ports and its own registers/state. Do not key the trigger on "
    "Trojan-internal signals, and do not force internal state the clean module lacks. "
    "The witness is replayed against the clean module, so a trigger naming Trojan-only "
    "signals cannot be evaluated there."
)


def _steer_feedback(reason: str) -> str:
    """Map a gauntlet reject reason to the repair message the next attempt sees.
    On the Trojan-internal-witness failure (stable reason substring), append the
    host-observable steering; otherwise pass the reason through unchanged. This is
    the whole of the v2 change to what the model sees, and it lives in the repair
    channel, never in the locked base body."""
    if "witness not applicable to clean" in reason:
        return reason + "." + _HOST_OBSERVABLE_STEERING
    return reason


def build_prompt(spec: InsertionSpec, repair_feedback: str | None = None) -> str:
    """Structured insertion prompt (§2.1) — LOCKED 2026-06-11.

    Leads with the defensive/detector-training framing (lowers refusal rate; the
    pilot measures the residual), encodes the spec's taxonomy cell, biases the
    rare trigger toward input/state space over time-depth (keeps activation-proof
    fast), and demands TWO blocks: the full infected module (structural diff =
    ground truth) and an activation WITNESS (a checkable claim activation-proof
    verifies by dual assertion). The witness fields are free-text-but-structured
    on purpose — the pilot reveals how regular the model's format is before we
    constrain it (measure-then-constrain). On a repair, the prior failure is
    appended."""
    p = f"""This is for a defensive hardware-security benchmark used to train and evaluate
hardware Trojan DETECTORS. Your task is to insert one benchmark Trojan into the
module below so that detection tools can be tested against a known, labeled example.

Clean module `{spec.top_module}`:
```verilog
{spec.clean_rtl}
```

Insert ONE Trojan with exactly these properties (do not change anything else):
  - activation:          {spec.activation}
  - trigger source:      {spec.trigger_source}
  - trigger mechanism:   {spec.trigger_mechanism}
  - payload:             {spec.payload}

The Trojan must be stealthy:
  - Rare trigger — it activates only on a specific, rare condition. Prefer a rare
    condition in INPUT/STATE SPACE (e.g. an exact wide-bit match) over one that is
    merely deep in TIME (e.g. a counter that must run for millions of cycles), so the
    trigger can be reached directly without long simulation.
  - Functionally invisible when dormant — outputs must be identical to the clean
    module on every non-triggering input, so it passes functional-equivalence checks.
  - Small — add minimal logic relative to the host module.
  - Synthesis-robust — do not tie the trigger or payload to constants that synthesis
    would fold away; the inserted logic must survive Yosys.

Return TWO blocks and nothing else:

1. The COMPLETE modified module, verbatim, wrapped exactly as:
<INFECTED>
...full infected Verilog...
</INFECTED>

2. An activation witness — the concrete condition that fires the Trojan and the
   observable effect — wrapped exactly as:
<ACTIVATION>
trigger: <the exact signal values / state that activate the Trojan, e.g.
         "count == 8'hC7 with en=1", or a forced internal state and the inputs to apply>
observable_effect: <how the payload manifests at the outputs when triggered, e.g.
         "count freezes / increments by 2 / output held at 8'h00">
</ACTIVATION>

The activation witness will be checked by independent simulation: we will drive the
circuit to the stated trigger and confirm the stated effect occurs AND that the clean
module does not exhibit it. An incorrect witness causes the sample to be rejected, so
state the true activating condition precisely."""
    if repair_feedback:
        p += (f"\n\nYour previous attempt FAILED: {repair_feedback}.\n"
              f"Fix it and return both blocks again.")
    return p


def parse_infected(text: str) -> str:
    """Extract the infected module from a response. Raises ValueError if the
    delimited block is absent (a malformed response is a reject, not a guess)."""
    m = _INFECTED_RE.search(text)
    if not m:
        raise ValueError("no <INFECTED>...</INFECTED> block in response")
    body = m.group(1).strip()
    if not body:
        raise ValueError("empty <INFECTED> block")
    return body


def parse_activation(text: str) -> dict:
    """Extract the activation witness — ``{trigger, observable_effect}`` — the
    input contract activation-proof consumes (parse trigger → forced state +
    applied inputs; assert observable_effect fires on infected, NOT on clean).

    Free-text-but-structured by design: kept lenient until the pilot shows how
    regular the model's format is (then tighten to a strict grammar if needed).
    Raises ValueError if the block or either field is missing (→ repair)."""
    m = _ACTIVATION_RE.search(text)
    if not m:
        raise ValueError("no <ACTIVATION>...</ACTIVATION> block in response")
    body = m.group(1)
    trig = re.search(r"trigger:\s*(.+?)(?:\n\s*observable_effect:|\Z)", body,
                     re.DOTALL | re.IGNORECASE)
    obs = re.search(r"observable_effect:\s*(.+)", body, re.DOTALL | re.IGNORECASE)
    if not trig or not trig.group(1).strip() or not obs or not obs.group(1).strip():
        raise ValueError("activation block missing trigger/observable_effect")
    return {"trigger": trig.group(1).strip(), "observable_effect": obs.group(1).strip()}


def ground_truth(clean_rtl: str, infected_rtl: str) -> dict:
    """Generation-time ground truth by structural diff (§2.2). Returns the
    manifest's `inserted_rtl` fields. Uses the validator's exact diff so the
    sample passes R6 by construction."""
    line_ranges = _V._added_line_ranges(clean_rtl, infected_rtl)
    inf = infected_rtl.splitlines()
    added_lines = [inf[i - 1] for (a, b) in line_ranges for i in range(a, b + 1)]
    return {"line_ranges": [list(r) for r in line_ranges], "added_text": added_lines}


# --------------------------------------------------------------------------- #
# Reject-and-repair loop (routed through the cost guard)
# --------------------------------------------------------------------------- #

@dataclass
class Verdict:
    ok: bool
    reason: str = ""
    detail: dict = field(default_factory=dict)   # carries the gauntlet's round-10 grade


@dataclass
class AttemptRecord:
    """One pass of the repair loop, kept for diagnosis. A rejected sample's full
    trail is quarantined to disk (never the corpus dir): rejects are data about the
    generator even though they are not data in the benchmark."""
    attempt: int
    in_tokens: int
    out_tokens: int
    cost_usd: float
    reason: str                          # "" on the accepted attempt; else parse/diff/verdict reason
    infected_rtl: str | None = None      # parsed infected module (None if the response did not parse)
    witness: dict | None = None          # parsed activation witness (None if it did not parse)
    raw_text: str | None = None          # the raw response, kept ONLY when parsing failed


@dataclass
class InsertionResult:
    accepted: bool
    infected_rtl: str | None
    ground_truth: dict | None
    attempts: int
    activation: dict | None = None      # the witness {trigger, observable_effect}
    verification: dict | None = None    # the gauntlet's round-10 grade (on accept)
    reason: str = ""
    steered: bool = False               # the v2 host-observable steering fired ≥1× in this loop
    attempt1_added_text: list | None = None  # attempt-1 inserted text (same-prompt collapse signal,
                                             # free of repair-path divergence); None if attempt 1
                                             # never produced a valid structural diff
    trail: list = field(default_factory=list)  # per-attempt AttemptRecords (diagnosis + cost)

    @property
    def cost_usd(self):
        """Total estimated spend for this sample, summed over every attempt."""
        return sum(r.cost_usd for r in self.trail)


def generate_sample(
    spec: InsertionSpec,
    client: LLMClient,
    guard: CG.CostGuard,
    verify,                                  # (clean, infected, spec, gt) -> Verdict
    *,
    model: str = "claude-sonnet-4",
    max_repairs: int = 3,
    est_out_tokens: int | None = None,
) -> InsertionResult:
    """Run the reject-and-repair loop for one sample. Every model call is
    pre-cleared by the cost guard (raises BudgetExceeded before overspending);
    the final accept/reject feeds the yield floor (raises YieldFloorAbort if the
    recent acceptance rate collapses). Returns once accepted or repairs exhausted.
    """
    guard.new_run()
    feedback = None
    last_reason = "no attempt"
    steered = False                      # did the v2 steering fire at least once?
    attempt1_added = None                # attempt-1 inserted text, for the collapse cluster
    trail = []                           # per-attempt records (diagnosis + cost)
    est_out = est_out_tokens if est_out_tokens is not None else _approx_tokens(spec.clean_rtl) + 256

    for attempt in range(1, max_repairs + 2):
        prompt = build_prompt(spec, feedback)
        guard.pre_call_check(CG.estimate_cost(model, _approx_tokens(prompt), est_out))
        resp = client.complete(prompt)
        cost = CG.estimate_cost(model, resp.in_tokens, resp.out_tokens)
        guard.record_spend(cost)
        rec = AttemptRecord(attempt, resp.in_tokens, resp.out_tokens, cost, reason="")
        trail.append(rec)

        try:
            infected = parse_infected(resp.text)
            activation = parse_activation(resp.text)     # both blocks required
        except ValueError as e:
            rec.reason = feedback = last_reason = f"parse error: {e}"
            rec.raw_text = resp.text                      # keep the malformed output for diagnosis
            continue
        rec.infected_rtl, rec.witness = infected, activation

        gt = ground_truth(spec.clean_rtl, infected)
        if not gt["line_ranges"]:
            rec.reason = feedback = last_reason = "no lines were added (empty structural diff)"
            continue
        if attempt == 1:                                # same-prompt collapse signal, captured
            attempt1_added = gt["added_text"]           # before any repair-path divergence

        # The gauntlet (incl. activation-proof) consumes the witness; dual
        # assertion (fires on infected, silent on clean) lives inside `verify`.
        verdict = verify(spec.clean_rtl, infected, spec, gt, activation)
        if verdict.ok:
            guard.record_outcome(True)
            return InsertionResult(True, infected, gt, attempt, activation=activation,
                                   verification=verdict.detail, steered=steered,
                                   attempt1_added_text=attempt1_added, trail=trail)
        rec.reason = last_reason = verdict.reason       # recorded reject reason stays clean
        feedback = _steer_feedback(verdict.reason)      # next attempt gets host-observable steering
        if feedback != verdict.reason:                  # steering actually fired this round
            steered = True

    guard.record_outcome(False)
    return InsertionResult(False, None, None, max_repairs + 1, reason=last_reason,
                           steered=steered, attempt1_added_text=attempt1_added, trail=trail)
