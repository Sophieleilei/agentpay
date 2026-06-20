"""Assemble what the SafetyGate service needs from provisioned state.

The service holds the agent wallet only to *submit* the settlement Payment once
every gate has passed. Gate verification is keyless — intake checks the agent's
signature against its on-chain DID, not against any key the service holds.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from ..config import ROOT, Settings, StateStore, load_policy
from ..pipeline.deps import Deps
from ..xrpl.client import get_client, load_wallet


@dataclass
class ServiceContext:
    deps: Deps
    recipient: str
    issuer: str


def load_sanctions() -> frozenset[str]:
    path = ROOT / "config" / "sanctions.json"
    if path.exists():
        return frozenset(json.loads(path.read_text()).get("blocked_addresses", []))
    return frozenset()


def build_context() -> ServiceContext:
    settings = Settings()
    store = StateStore()
    agent_acct = store.account("agent")
    recipient_acct = store.account("recipient")
    issuer_acct = store.account("issuer")
    if not (agent_acct and recipient_acct and issuer_acct):
        raise SystemExit("accounts not provisioned — run: python scripts/00_setup_accounts.py")

    deps = Deps(
        client=get_client(settings.json_rpc),
        settings=settings,
        policy=load_policy(),
        store=store,
        issuer_address=issuer_acct["address"],
        agent_wallet=load_wallet(settings.seed("agent") or agent_acct["seed"]),
        sanctions=load_sanctions(),
    )
    return ServiceContext(deps=deps, recipient=recipient_acct["address"],
                          issuer=issuer_acct["address"])
