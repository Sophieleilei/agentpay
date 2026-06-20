"""Agent-side helpers: shape a draft into a signed PaymentIntent.

This is where 'autonomous' comes from — the agent holds its own seed and signs
its own intents in code. No wallet UI, no human clicking approve.
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, Field
from xrpl.core import keypairs
from xrpl.wallet import Wallet

from ..models import PaymentIntent


class IntentDraft(BaseModel):
    """The autonomy surface — what the AI agent decides. Identity, signing, and
    the on-chain plumbing are added deterministically afterward."""

    amount: float = Field(description="How much to pay, in RLUSD", gt=0)
    purpose: str = Field(description="Why: settlement | data_purchase | compute")
    jurisdiction: str = Field(description="Counterparty jurisdiction, ISO-3166 alpha-2")
    reasoning: str = Field(default="", description="One line on why this amount/purpose")


def sign_intent(intent: PaymentIntent, wallet: Wallet) -> PaymentIntent:
    """Attach the agent's public key and a signature over the canonical payload."""
    intent.public_key = wallet.public_key
    intent.signature = keypairs.sign(intent.signing_payload(), wallet.private_key)
    return intent


def build_intent(draft: IntentDraft, agent_wallet: Wallet, recipient: str) -> PaymentIntent:
    """Draft → fully-formed, signed PaymentIntent ready for the pipeline."""
    intent = PaymentIntent(
        agent_address=agent_wallet.address,
        recipient=recipient,
        amount=draft.amount,
        purpose=draft.purpose,
        jurisdiction=draft.jurisdiction,
        nonce=uuid.uuid4().hex,
    )
    return sign_intent(intent, agent_wallet)
