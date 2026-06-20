"""Gate 4 — sanctions. Screen the counterparty.

The pass/fail call is deterministic: an exact hit on the sanctions set rejects.
(An LLM may *propose* fuzzy-match candidates for a human to review, but it never
makes the decision — so it can't be prompt-injected into clearing a hit.)
"""
from __future__ import annotations

from ...models import AuditEntry
from ..deps import Deps
from ..state import PipelineState

GATE = "sanctions"


def run(state: PipelineState, deps: Deps) -> AuditEntry:
    recipient = state.intent.recipient

    if recipient in deps.sanctions:
        return AuditEntry(gate=GATE, status="fail",
                          reason="counterparty is on the sanctions list",
                          evidence={"recipient": recipient})

    return AuditEntry(gate=GATE, status="pass", reason="counterparty cleared",
                      evidence={"recipient": recipient, "list_size": len(deps.sanctions)})
