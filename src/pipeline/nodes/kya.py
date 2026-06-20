"""Gate 2 — KYA (Know Your Agent).

Read-only ledger check: the agent holds a live, accepted credential from the
trusted issuer, AND the recipient's permissioned domain accepts that exact
(issuer, credential_type). The credential id found here is what settle later
presents on-chain.
"""
from __future__ import annotations

from ...models import AuditEntry
from ...xrpl.credentials import verify_credential
from ...xrpl.domains import domain_accepts
from ..deps import Deps
from ..state import PipelineState

GATE = "kya"


def run(state: PipelineState, deps: Deps) -> AuditEntry:
    intent = state.intent

    status = verify_credential(deps.client, intent.agent_address, deps.issuer_address)
    if not status.valid:
        return AuditEntry(gate=GATE, status="fail", reason=status.reason,
                          evidence={"found": status.found, "accepted": status.accepted,
                                    "expired": status.expired})

    if not domain_accepts(deps.client, intent.recipient, deps.issuer_address):
        return AuditEntry(gate=GATE, status="fail",
                          reason="recipient's permissioned domain does not accept this credential")

    state.credential_id = status.credential_id
    return AuditEntry(
        gate=GATE, status="pass", reason="credential matched permissioned domain",
        evidence={"credential_id": status.credential_id, "issuer": deps.issuer_address},
    )
