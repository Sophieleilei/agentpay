"""Agent identity via XLS-40 DID.

The agent publishes its signing public key on-chain in a DID object owned by its
account. The intake gate resolves that key (read-only) to verify the agent
actually signed the intent — binding the request to the on-chain identity.
"""
from __future__ import annotations

from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountObjects
from xrpl.models.transactions import DIDSet
from xrpl.wallet import Wallet

from .client import submit


def set_did(client: JsonRpcClient, wallet: Wallet) -> dict:
    """Publish the wallet's public key as the agent's DID document data."""
    return submit(DIDSet(account=wallet.address, data=wallet.public_key), wallet, client)


def resolve_public_key(client: JsonRpcClient, address: str) -> str | None:
    """Read-only: return the public key the account published in its DID, or
    None if it has none."""
    response = client.request(AccountObjects(account=address))
    for obj in response.result.get("account_objects", []):
        if obj.get("LedgerEntryType") == "DID":
            return obj.get("Data")
    return None
