"""Pipeline state — the object that flows through the deterministic gates.

This is the Pydantic AI / hand-rolled equivalent of a graph state: an intent
plus an accumulating audit trail and a terminal decision. No framework owns it;
the runner threads it gate to gate.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from ..models import AuditEntry, Decision, PaymentIntent


class PipelineState(BaseModel):
    intent: PaymentIntent
    audit_trail: list[AuditEntry] = Field(default_factory=list)
    decision: Decision = "pending"
    reject_reason: str = ""
    # Set by the KYA gate, consumed by settle.
    credential_id: str | None = None
    tx_hash: str | None = None
    explorer_url: str | None = None

    def record(self, entry: AuditEntry) -> None:
        self.audit_trail.append(entry)
