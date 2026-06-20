"""Recipient-side gating: permissioned domain + deposit authorization.

The merchant/recipient declares which (issuer, credential_type) pairs it trusts
— as a permissioned domain (XLS-80) for the KYA match check, and as
DepositPreauth credentials so the ledger itself only accepts a credential-bearing
payment. Set once at provisioning; read-only thereafter.
"""
from __future__ import annotations

from xrpl.clients import JsonRpcClient
from xrpl.models.requests import AccountObjects
from xrpl.models.transactions import (
    AccountSet,
    AccountSetAsfFlag,
    DepositPreauth,
    PermissionedDomainSet,
)
from xrpl.models.transactions.deposit_preauth import Credential as AuthCredential
from xrpl.models.transactions.permissioned_domain_set import Credential as DomainCredential
from xrpl.wallet import Wallet

from .client import CREDENTIAL_TYPE, created_index, hexstr, submit


def configure_recipient(
    client: JsonRpcClient,
    recipient: Wallet,
    issuer: str,
    credential_type: str = CREDENTIAL_TYPE,
) -> dict:
    """Stand up the full recipient gate in one call. Returns the domain id."""
    ct = hexstr(credential_type)

    domain_res = submit(
        PermissionedDomainSet(
            account=recipient.address,
            accepted_credentials=[DomainCredential(issuer=issuer, credential_type=ct)],
        ),
        recipient,
        client,
    )
    domain_id = created_index(domain_res, "PermissionedDomain") or _existing_domain(client, recipient.address)

    submit(
        AccountSet(account=recipient.address, set_flag=AccountSetAsfFlag.ASF_DEPOSIT_AUTH),
        recipient,
        client,
    )
    submit(
        DepositPreauth(
            account=recipient.address,
            authorize_credentials=[AuthCredential(issuer=issuer, credential_type=ct)],
        ),
        recipient,
        client,
    )
    return {"domain_id": domain_id, "issuer": issuer, "credential_type": credential_type}


def _existing_domain(client: JsonRpcClient, address: str) -> str | None:
    response = client.request(AccountObjects(account=address))
    for obj in response.result.get("account_objects", []):
        if obj.get("LedgerEntryType") == "PermissionedDomain":
            return obj.get("index")
    return None


def domain_accepts(
    client: JsonRpcClient,
    recipient: str,
    issuer: str,
    credential_type: str = CREDENTIAL_TYPE,
) -> bool:
    """Read-only: does the recipient's permissioned domain accept this exact
    (issuer, credential_type)?"""
    ct = hexstr(credential_type)
    response = client.request(AccountObjects(account=recipient))
    for obj in response.result.get("account_objects", []):
        if obj.get("LedgerEntryType") != "PermissionedDomain":
            continue
        for wrapper in obj.get("AcceptedCredentials", []):
            cred = wrapper.get("Credential", wrapper)
            if cred.get("Issuer") == issuer and cred.get("CredentialType") == ct:
                return True
    return False
