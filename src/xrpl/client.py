"""Thin helpers over xrpl-py: client, wallets, submit, ledger lookups.

Importing this module also installs a one-line compatibility shim: xrpl-py
5.0.0 serializes a Payment's ``credential_ids`` to ``CredentialIds``, but the
ledger field is ``CredentialIDs`` — without the fix the binary codec raises
KeyError and no credential-bearing payment can ever be signed. Teaching the
abbreviation table the ``ids -> IDs`` plural fixes it project-wide. Verified on
Devnet (see validate_chain.py).
"""
from __future__ import annotations

import xrpl.models.base_model as _bm

_bm.ABBREVIATIONS.setdefault("ids", "IDs")

from xrpl.account import get_balance
from xrpl.clients import JsonRpcClient
from xrpl.transaction import submit_and_wait
from xrpl.wallet import Wallet, generate_faucet_wallet

CREDENTIAL_TYPE = "KYA_TIER1"


def hexstr(value: str) -> str:
    """ASCII -> uppercase hex, as XRPL expects for blob fields."""
    return value.encode("ascii").hex().upper()


def get_client(url: str) -> JsonRpcClient:
    return JsonRpcClient(url)


def fund_wallet(client: JsonRpcClient) -> Wallet:
    return generate_faucet_wallet(client, debug=False)


def load_wallet(seed: str) -> Wallet:
    return Wallet.from_seed(seed)


def balance_xrp(client: JsonRpcClient, address: str) -> float:
    try:
        return float(get_balance(address, client)) / 1_000_000
    except Exception:
        return 0.0


class XRPLError(RuntimeError):
    """A submitted transaction did not reach tesSUCCESS."""

    def __init__(self, engine_result: str, tx_type: str):
        self.engine_result = engine_result
        super().__init__(f"{tx_type} failed on-ledger: {engine_result}")


def submit(transaction, wallet: Wallet, client: JsonRpcClient) -> dict:
    """Sign, submit, and wait for validation. Raises XRPLError on a non-success
    engine result — the caller can let it surface as a failed gate."""
    response = submit_and_wait(transaction, client, wallet)
    result = response.result
    engine = result.get("meta", {}).get("TransactionResult", "")
    if engine != "tesSUCCESS":
        raise XRPLError(engine, transaction.transaction_type)
    return result


def created_index(result: dict, ledger_entry_type: str) -> str | None:
    """Pull the LedgerIndex of a node this transaction created (e.g. the
    PermissionedDomain id)."""
    for node in result.get("meta", {}).get("AffectedNodes", []):
        created = node.get("CreatedNode")
        if created and created.get("LedgerEntryType") == ledger_entry_type:
            return created.get("LedgerIndex")
    return None
