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

from . import cost_guard as CG
from . import validate as _V

# The model must wrap the full infected module so we can diff it structurally.
_INFECTED_RE = re.compile(r"<INFECTED>\s*(.*?)\s*</INFECTED>", re.DOTALL)


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


def build_prompt(spec: InsertionSpec, repair_feedback: str | None = None) -> str:
    """Structured insertion prompt (§2.1). DRAFT content — review before pilot.

    Encodes the taxonomy and demands the full infected module wrapped in
    <INFECTED></INFECTED> so ground truth can be a structural diff, never a
    keyword scan. On a repair, the prior failure is appended."""
    tgt = f"\n- target net: {spec.target_net}" if spec.target_net else ""
    p = f"""You insert a single hardware Trojan into a Verilog module for a research benchmark.

Clean module `{spec.top_module}`:
```verilog
{spec.clean_rtl}
```

Insert ONE Trojan with these properties (do not change anything else):
- activation: {spec.activation}
- trigger source: {spec.trigger_source}
- trigger mechanism: {spec.trigger_mechanism}
- payload: {spec.payload}{tgt}

Constraints: the Trojan must be stealthy (small, rarely activated), must still
compile and simulate, and must survive synthesis (not be optimized away). Return
the COMPLETE modified module verbatim, wrapped exactly as:
<INFECTED>
...full infected Verilog...
</INFECTED>"""
    if repair_feedback:
        p += f"\n\nYour previous attempt FAILED: {repair_feedback}\nFix it and return the full module again."
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


@dataclass
class InsertionResult:
    accepted: bool
    infected_rtl: str | None
    ground_truth: dict | None
    attempts: int
    reason: str = ""


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
    est_out = est_out_tokens if est_out_tokens is not None else _approx_tokens(spec.clean_rtl) + 256

    for attempt in range(1, max_repairs + 2):
        prompt = build_prompt(spec, feedback)
        guard.pre_call_check(CG.estimate_cost(model, _approx_tokens(prompt), est_out))
        resp = client.complete(prompt)
        guard.record_spend(CG.estimate_cost(model, resp.in_tokens, resp.out_tokens))

        try:
            infected = parse_infected(resp.text)
        except ValueError as e:
            feedback = last_reason = f"parse error: {e}"
            continue

        gt = ground_truth(spec.clean_rtl, infected)
        if not gt["line_ranges"]:
            feedback = last_reason = "no lines were added (empty structural diff)"
            continue

        verdict = verify(spec.clean_rtl, infected, spec, gt)
        if verdict.ok:
            guard.record_outcome(True)
            return InsertionResult(True, infected, gt, attempt)
        feedback = last_reason = verdict.reason

    guard.record_outcome(False)
    return InsertionResult(False, None, None, max_repairs + 1, last_reason)
