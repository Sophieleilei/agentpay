"""KYA credentials on the XRP Ledger — issue, accept, and **verify**.

`verify_credential` is the heart of SafetyGate: a deterministic, read-only
ledger lookup that answers one question — *does this agent hold a live, accepted
credential from a trusted issuer?* Every gate decision ultimately leans on it,
and it never writes to the ledger.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from xrpl.clients import JsonRpcClient
from xrpl.models.requests import LedgerEntry
from xrpl.models.requests.ledger_entry import Credential as CredentialLookup
from xrpl.models.transactions import CredentialAccept, CredentialCreate
from xrpl.wallet import Wallet

from .client import CREDENTIAL_TYPE, hexstr, submit

LSF_ACCEPTED = 0x00010000
RIPPLE_EPOCH = 946684800  # seconds between Unix epoch and the XRPL epoch


@dataclass
class CredentialStatus:
    found: bool
    accepted: bool
    expired: bool
    credential_id: str | None = None
    issuer: str | None = None
    subject: str | None = None
    reason: str = ""

    @property
    def valid(self) -> bool:
        """Fail-closed: only a found + accepted + unexpired credential is valid."""
        return self.found and self.accepted and not self.expired


def issue_credential(
    client: JsonRpcClient,
    issuer: Wallet,
    subject: str,
    credential_type: str = CREDENTIAL_TYPE,
    expiration: int | None = None,
) -> dict:
    return submit(
        CredentialCreate(
            account=issuer.address,
            subject=subject,
            credential_type=hexstr(credential_type),
            expiration=expiration,
        ),
        issuer,
        client,
    )


def accept_credential(
    client: JsonRpcClient,
    subject: Wallet,
    issuer: str,
    credential_type: str = CREDENTIAL_TYPE,
) -> dict:
    return submit(
        CredentialAccept(
            account=subject.address,
            issuer=issuer,
            credential_type=hexstr(credential_type),
        ),
        subject,
        client,
    )


def verify_credential(
    client: JsonRpcClient,
    subject: str,
    issuer: str,
    credential_type: str = CREDENTIAL_TYPE,
) -> CredentialStatus:
    """Read-only. Look the credential up by (subject, issuer, type) and report
    whether it is a live, accepted credential. Absence is failure, not error."""
    request = LedgerEntry(
        credential=CredentialLookup(
            subject=subject,
            issuer=issuer,
            credential_type=hexstr(credential_type),
        ),
        ledger_index="validated",
    )
    response = client.request(request)
    result = response.result

    if "node" not in result:
        return CredentialStatus(
            found=False, accepted=False, expired=False,
            issuer=issuer, subject=subject,
            reason="no credential from this issuer for this agent",
        )

    node = result["node"]
    accepted = bool(node.get("Flags", 0) & LSF_ACCEPTED)
    expiration = node.get("Expiration")
    expired = expiration is not None and expiration <= int(time.time()) - RIPPLE_EPOCH

    reason = "valid"
    if not accepted:
        reason = "credential issued but never accepted by the agent"
    elif expired:
        reason = "credential expired"

    return CredentialStatus(
        found=True,
        accepted=accepted,
        expired=expired,
        credential_id=result.get("index"),
        issuer=issuer,
        subject=subject,
        reason=reason,
    )
