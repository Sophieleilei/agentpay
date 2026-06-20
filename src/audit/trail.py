"""Render the decision chain — the replayable record of why a payment did or
did not happen."""
from __future__ import annotations

import json

from ..pipeline.state import PipelineState

_MARK = {"pass": "✔", "fail": "✘", "hold": "⏸"}
_DECISION = {"approved": "APPROVED ✅", "rejected": "REJECTED ⛔",
             "held": "HELD FOR APPROVAL ⏸", "pending": "PENDING"}


def render(state: PipelineState) -> str:
    intent = state.intent
    lines = [
        f"intent  : {intent.amount} {intent.currency} → {intent.recipient}",
        f"          purpose={intent.purpose} jurisdiction={intent.jurisdiction} "
        f"nonce={intent.nonce}",
        "",
    ]
    for e in state.audit_trail:
        lines.append(f"  {_MARK.get(e.status, '?')} {e.gate:9} {e.reason}")
    lines.append("")
    lines.append(f"decision: {_DECISION.get(state.decision, state.decision)}")
    if state.tx_hash:
        lines.append(f"on-chain: {state.tx_hash}")
        if state.explorer_url:
            lines.append(f"explorer: {state.explorer_url}")
    else:
        lines.append("on-chain: NONE — nothing settled, zero ledger footprint")
    return "\n".join(lines)


def to_json(state: PipelineState) -> str:
    return json.dumps(state.model_dump(), indent=2)
