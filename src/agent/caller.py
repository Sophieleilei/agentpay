"""A demo AI-agent *caller* of SafetyGate — deterministic, no LLM.

This stands in for whatever external agent wants to pay. Its decision logic is a
plain heuristic; a real agent could use any model. The point is the HTTP
contract: plan an intent, run the x402 two-phase call against the gate, read the
verdict. SafetyGate itself never sees the agent's reasoning — only the intent.

    python -m src.agent.caller --task "Pay vendor X 3000 RLUSD for the data bundle"
"""
from __future__ import annotations

import argparse
import re
import uuid

import httpx
from xrpl.core import keypairs
from xrpl.wallet import Wallet

from ..config import Settings, StateStore
from ..xrpl.client import load_wallet
from .tools import IntentDraft

DEFAULT_GATE = "http://127.0.0.1:8000"


def plan(task: str) -> IntentDraft:
    """Deterministic stand-in for an agent's reasoning."""
    t = task.lower()
    match = re.search(r"(\d[\d,]*)", t)
    amount = float(match.group(1).replace(",", "")) if match else (8000.0 if "premium" in t else 3000.0)
    if "compute" in t:
        purpose = "compute"
    elif "data" in t or "bundle" in t:
        purpose = "data_purchase"
    else:
        purpose = "settlement"
    return IntentDraft(amount=amount, purpose=purpose, jurisdiction="CH",
                       reasoning="deterministic heuristic")


def load_caller() -> tuple[Wallet, str]:
    """The agent's own wallet (to sign intents) + the merchant it pays."""
    settings = Settings()
    store = StateStore()
    agent = store.account("agent")
    recipient = store.account("recipient")
    if not (agent and recipient):
        raise SystemExit("accounts not provisioned — run: python scripts/00_setup_accounts.py")
    return load_wallet(settings.seed("agent") or agent["seed"]), recipient["address"]


def call_gate(base_url: str, wallet: Wallet, recipient: str, draft: IntentDraft) -> dict:
    """Run the x402 two-phase handshake and return the gate's verdict."""
    body = {
        "agent_address": wallet.address, "recipient": recipient,
        "amount": draft.amount, "purpose": draft.purpose,
        "jurisdiction": draft.jurisdiction, "nonce": uuid.uuid4().hex,
    }

    # Phase 1: no signature → expect 402 with the payload to sign.
    challenge = httpx.post(f"{base_url}/intent", json=body, timeout=60)
    if challenge.status_code != 402:
        return {"phase": 1, "status": challenge.status_code, "body": challenge.json()}

    payload_hex = challenge.json()["payload_to_sign_hex"]
    signature = keypairs.sign(bytes.fromhex(payload_hex), wallet.private_key)

    # Phase 2: signed → the verdict.
    signed = {**body, "public_key": wallet.public_key, "signature": signature}
    verdict = httpx.post(f"{base_url}/intent", json=signed, timeout=60)
    return {"phase": 2, "status": verdict.status_code,
            "challenge": challenge.json(), "body": verdict.json()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Call SafetyGate with an agent intent")
    parser.add_argument("--task", required=True)
    parser.add_argument("--gate-url", default=DEFAULT_GATE)
    args = parser.parse_args()

    wallet, recipient = load_caller()
    draft = plan(args.task)
    print(f"[agent] intent: {draft.amount} RLUSD · {draft.purpose} · {draft.jurisdiction}"
          f"  ({draft.reasoning})")
    result = call_gate(args.gate_url, wallet, recipient, draft)
    body = result["body"]
    print(f"[gate ] HTTP {result['status']} · decision={body.get('decision')}")
    if body.get("reject_reason"):
        print(f"        reason: {body['reject_reason']}")
    if body.get("tx_hash"):
        print(f"        settled: {body['explorer_url']}")


if __name__ == "__main__":
    main()
