"""The compliance pipeline runner — deterministic, fail-closed, no framework.

First principle: **any gate that does not pass stops the pipeline.** A `fail`
becomes `rejected`, a `hold` becomes `held`, and in either case settle never
runs — so a non-compliant intent leaves zero on-chain footprint. The only path
to an on-chain settlement is every gate returning `pass`.

The gates are a plain ordered list. Safety is topological: you cannot reach
settle without traversing intake → kya → policy → sanctions first.
"""
from __future__ import annotations

from ..models import PaymentIntent
from .deps import Deps
from .nodes import intake, kya, policy, sanctions, settle
from .state import PipelineState

# Order matters: identity → know-your-agent → policy → sanctions → settle.
GATES = [intake, kya, policy, sanctions, settle]


def run_pipeline(intent: PaymentIntent, deps: Deps) -> PipelineState:
    state = PipelineState(intent=intent)

    for gate in GATES:
        entry = gate.run(state, deps)
        state.record(entry)

        if entry.status == "fail":
            state.decision = "rejected"
            state.reject_reason = entry.reason
            return state
        if entry.status == "hold":
            state.decision = "held"
            state.reject_reason = entry.reason
            return state

    state.decision = "approved"
    return state
