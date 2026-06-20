"""Core data models shared across the agent, pipeline, and XRPL layers."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Decision = Literal["pending", "approved", "rejected", "held"]
GateStatus = Literal["pass", "fail", "hold"]


class PaymentIntent(BaseModel):
    """What an autonomous agent wants to do. Produced by the AI layer, then
    frozen and run through the deterministic compliance pipeline."""

    agent_address: str = Field(description="Payer — the agent's XRPL r-address")
    recipient: str = Field(description="Counterparty / authorizer r-address")
    amount: float = Field(description="Value in RLUSD", gt=0)
    currency: str = "RLUSD"
    jurisdiction: str = Field(description="Counterparty jurisdiction, ISO-3166 alpha-2")
    purpose: str = Field(description="Why the payment is happening")
    nonce: str = Field(description="Unique per-intent replay guard")
    credential_id: str | None = None
    # Filled when the agent signs; verified at the intake gate.
    public_key: str | None = None
    signature: str | None = None

    def signing_payload(self) -> bytes:
        """Canonical bytes the agent signs — every field except the signature
        envelope. Deterministic key ordering so verification is reproducible."""
        body = self.model_dump(exclude={"signature", "public_key"})
        return json.dumps(body, sort_keys=True, separators=(",", ":")).encode()

    def fingerprint(self) -> str:
        return hashlib.sha256(self.signing_payload()).hexdigest()[:16]


class AuditEntry(BaseModel):
    """One immutable record per gate. The chain of these IS the audit trail."""

    gate: str
    status: GateStatus
    reason: str
    evidence: dict = Field(default_factory=dict)
    ts: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Policy(BaseModel):
    per_tx_limit: float
    daily_limit: float
    approval_threshold: float
    allowed_jurisdictions: list[str]
    blocked_jurisdictions: list[str]
    allowed_purposes: list[str]
