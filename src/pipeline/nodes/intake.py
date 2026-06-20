"""Gate 1 — intake. Bind the request to the on-chain agent identity.

Verify the intent was signed by the key the agent published in its DID. No
valid signature over a DID-resolved key → fail, and the pipeline stops here.
"""
from __future__ import annotations

from xrpl.core.keypairs import is_valid_message

from ...models import AuditEntry
from ...xrpl.did import resolve_public_key
from ..deps import Deps
from ..state import PipelineState

GATE = "intake"


def run(state: PipelineState, deps: Deps) -> AuditEntry:
    intent = state.intent

    if not intent.signature or not intent.public_key:
        return AuditEntry(gate=GATE, status="fail", reason="intent is unsigned")

    published = resolve_public_key(deps.client, intent.agent_address)
    if published is None:
        return AuditEntry(gate=GATE, status="fail",
                          reason="agent has no on-chain DID to verify against")
    if published.upper() != intent.public_key.upper():
        return AuditEntry(gate=GATE, status="fail",
                          reason="signing key does not match the agent's published DID")

    try:
        ok = is_valid_message(
            intent.signing_payload(), bytes.fromhex(intent.signature), intent.public_key
        )
    except Exception:
        ok = False
    if not ok:
        return AuditEntry(gate=GATE, status="fail",
                          reason="signature does not verify against the DID key")

    return AuditEntry(
        gate=GATE, status="pass", reason="identity verified via DID",
        evidence={"agent": intent.agent_address, "key": f"{published[:14]}…"},
    )
