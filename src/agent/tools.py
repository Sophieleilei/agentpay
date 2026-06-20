"""The autonomy surface — what a calling agent decides before SafetyGate sees
anything. Identity and signing happen in the caller; the gate only ever
receives a finished intent."""
from __future__ import annotations

from pydantic import BaseModel, Field


class IntentDraft(BaseModel):
    amount: float = Field(description="How much to pay, in RLUSD", gt=0)
    purpose: str = Field(description="Why: settlement | data_purchase | compute")
    jurisdiction: str = Field(description="Counterparty jurisdiction, ISO-3166 alpha-2")
    reasoning: str = Field(default="", description="One line on why this amount/purpose")
