"""Settlement — the single write touchpoint.

Everything upstream is read-only ledger inspection. Only here, and only after
every gate has passed, does a transaction reach the chain: an x402 payment
handshake followed by a credential-bearing Payment that clears the recipient's
deposit-auth gate. A rejected intent never gets this far, so it leaves zero
on-chain footprint.
"""
from __future__ import annotations

import hashlib
import json

from xrpl.clients import JsonRpcClient
from xrpl.models.transactions import Memo, Payment
from xrpl.utils import xrp_to_drops
from xrpl.wallet import Wallet

from .client import XRPLError, hexstr, submit


def _x402_handshake(amount_rlusd: float, recipient: str, credential_id: str) -> dict:
    """Model the x402 402-handshake: the resource demands payment, the agent
    answers with an authorization referencing its KYA credential. (No network
    round-trip in the demo — the structure is what matters.)"""
    return {
        "challenge": {
            "status": 402,
            "accepts": [{"scheme": "xrpl", "amount_rlusd": amount_rlusd, "pay_to": recipient}],
        },
        "authorization": {
            "scheme": "xrpl",
            "credential_id": credential_id,
            "settled_via": "Payment+CredentialIDs",
        },
    }


def settle(
    client: JsonRpcClient,
    payer: Wallet,
    recipient: str,
    amount_rlusd: float,
    xrp_per_rlusd: float,
    credential_id: str,
    purpose: str,
    explorer: str,
) -> dict:
    """Run the handshake and submit the on-chain settlement. Raises XRPLError
    if the ledger rejects it (e.g. the deposit-auth gate)."""
    handshake = _x402_handshake(amount_rlusd, recipient, credential_id)

    # Symbolic on-chain amount kept within faucet balances; the true RLUSD
    # figure rides along in the memo and invoice id.
    amount_xrp = round(amount_rlusd * xrp_per_rlusd, 6)
    invoice_id = hashlib.sha256(
        f"{payer.address}:{recipient}:{amount_rlusd}:{purpose}".encode()
    ).hexdigest().upper()
    memo = Memo(
        memo_type=hexstr("safetygate/settlement"),
        memo_data=hexstr(json.dumps({
            "amount_rlusd": amount_rlusd,
            "currency": "RLUSD",
            "purpose": purpose,
            "credential_id": credential_id,
        }, separators=(",", ":"))),
    )

    result = submit(
        Payment(
            account=payer.address,
            destination=recipient,
            amount=xrp_to_drops(amount_xrp),
            credential_ids=[credential_id],
            invoice_id=invoice_id,
            memos=[memo],
        ),
        payer,
        client,
    )

    tx_hash = result["hash"]
    return {
        "tx_hash": tx_hash,
        "amount_rlusd": amount_rlusd,
        "amount_xrp": amount_xrp,
        "invoice_id": invoice_id,
        "handshake": handshake,
        "explorer_url": f"{explorer}/transactions/{tx_hash}",
    }


__all__ = ["settle", "XRPLError"]
