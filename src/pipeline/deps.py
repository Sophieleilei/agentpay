"""Everything the gates read from. Assembled once per run."""
from __future__ import annotations

from dataclasses import dataclass

from xrpl.clients import JsonRpcClient
from xrpl.wallet import Wallet

from ..config import Settings, StateStore
from ..models import Policy


@dataclass
class Deps:
    client: JsonRpcClient
    settings: Settings
    policy: Policy
    store: StateStore
    issuer_address: str
    # Present only when the agent itself is driving settlement (it holds the seed).
    agent_wallet: Wallet | None = None
    sanctions: frozenset[str] = frozenset()
