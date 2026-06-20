"""Gate 5 — settle. The only gate that writes to the ledger.

Reached only when every prior gate passed. Runs the x402 handshake and submits
the credential-bearing Payment. If the ledger's own deposit-auth gate rejects
it, that surfaces as a failed gate — never a silent partial settlement.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ...models import AuditEntry
from ...xrpl.client import XRPLError
from ...xrpl.settlement import settle as settle_payment
from ..deps import Deps
from ..state import PipelineState

GATE = "settle"


def run(state: PipelineState, deps: Deps) -> AuditEntry:
    intent = state.intent

    if deps.agent_wallet is None:
        return AuditEntry(gate=GATE, status="fail",
                          reason="no agent wallet available to sign settlement")
    if state.credential_id is None:
        return AuditEntry(gate=GATE, status="fail",
                          reason="no verified credential to present on-chain")

    try:
        result = settle_payment(
            client=deps.client,
            payer=deps.agent_wallet,
            recipient=intent.recipient,
            amount_rlusd=intent.amount,
            xrp_per_rlusd=deps.settings.xrp_per_rlusd,
            credential_id=state.credential_id,
            purpose=intent.purpose,
            explorer=deps.settings.explorer,
        )
    except XRPLError as exc:
        return AuditEntry(gate=GATE, status="fail",
                          reason=f"ledger rejected settlement: {exc.engine_result}")

    state.tx_hash = result["tx_hash"]
    state.explorer_url = result["explorer_url"]
    deps.store.record_spend(
        intent.agent_address, datetime.now(timezone.utc).date().isoformat(), intent.amount
    )
    return AuditEntry(
        gate=GATE, status="pass", reason="x402 settled · RLUSD transferred",
        evidence={"tx_hash": result["tx_hash"], "amount_xrp": result["amount_xrp"],
                  "invoice_id": result["invoice_id"], "explorer": result["explorer_url"]},
    )
