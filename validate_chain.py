"""One-shot Devnet proof that the whole credential -> gate -> settlement chain
actually happens on this network. Run before trusting any service code.

    .venv/bin/python validate_chain.py
"""
from __future__ import annotations

# xrpl-py 5.0.0 mis-cases credential_ids -> "CredentialIds"; the ledger field is
# "CredentialIDs". Teach the abbreviation table the plural before any model use.
import xrpl.models.base_model as _bm
_bm.ABBREVIATIONS["ids"] = "IDs"

from xrpl.clients import JsonRpcClient
from xrpl.models.requests import LedgerEntry
from xrpl.models.requests.ledger_entry import Credential as CredentialLookup
from xrpl.models.transactions import (
    AccountSet,
    AccountSetAsfFlag,
    CredentialAccept,
    CredentialCreate,
    DepositPreauth,
    PermissionedDomainSet,
    Payment,
)
from xrpl.models.transactions.deposit_preauth import Credential as AuthCredential
from xrpl.models.transactions.permissioned_domain_set import Credential as DomainCredential
from xrpl.transaction import submit_and_wait
from xrpl.asyncio.transaction.reliable_submission import XRPLReliableSubmissionException
from xrpl.utils import xrp_to_drops
from xrpl.wallet import generate_faucet_wallet

ENDPOINT = "https://s.devnet.rippletest.net:51234"
CRED_TYPE = "KYC".encode().hex().upper()
LSF_ACCEPTED = 0x00010000

client = JsonRpcClient(ENDPOINT)


def send(tx, wallet, label, allow_fail=False):
    try:
        res = submit_and_wait(tx, client, wallet).result
        code = res.get("meta", {}).get("TransactionResult")
    except XRPLReliableSubmissionException as exc:
        # submit_and_wait raises on tec* codes — recover the engine result.
        res, code = {}, str(exc).rsplit(":", 1)[-1].strip()
    print(f"  {label:36} {code}")
    if not allow_fail and code != "tesSUCCESS":
        raise SystemExit(f"FAILED at {label}: {code}")
    return res, code


print("1) funding alice / recipient / issuer from faucet ...")
alice = generate_faucet_wallet(client, debug=False)      # agent / payer
recipient = generate_faucet_wallet(client, debug=False)  # counterparty
issuer = generate_faucet_wallet(client, debug=False)     # KYA issuer
for n, w in [("ALICE", alice), ("RECIPIENT", recipient), ("ISSUER", issuer)]:
    print(f"   {n:10} {w.classic_address}  seed={w.seed}")

print("\n2) issuer -> CredentialCreate(subject=alice)")
send(CredentialCreate(account=issuer.classic_address, subject=alice.classic_address,
                      credential_type=CRED_TYPE), issuer, "CredentialCreate")

print("3) alice -> CredentialAccept")
send(CredentialAccept(account=alice.classic_address, issuer=issuer.classic_address,
                      credential_type=CRED_TYPE), alice, "CredentialAccept")

print("4) ledger_entry: look up the credential (the heart of verifyCredential)")
le = client.request(LedgerEntry(
    credential=CredentialLookup(subject=alice.classic_address,
                                issuer=issuer.classic_address,
                                credential_type=CRED_TYPE),
    ledger_index="validated",
)).result
node = le["node"]
cred_id = le["index"]
accepted = bool(node.get("Flags", 0) & LSF_ACCEPTED)
print(f"   credential id : {cred_id}")
print(f"   lsfAccepted   : {accepted}")
print(f"   flags         : {hex(node.get('Flags', 0))}")
if not accepted:
    raise SystemExit("credential not accepted — gate would never pass")

print("\n5) recipient -> PermissionedDomainSet + DepositAuth + DepositPreauth(by credential)")
send(PermissionedDomainSet(account=recipient.classic_address,
     accepted_credentials=[DomainCredential(issuer=issuer.classic_address,
                                             credential_type=CRED_TYPE)]),
     recipient, "PermissionedDomainSet")
send(AccountSet(account=recipient.classic_address,
                set_flag=AccountSetAsfFlag.ASF_DEPOSIT_AUTH),
     recipient, "AccountSet(asfDepositAuth)")
send(DepositPreauth(account=recipient.classic_address,
     authorize_credentials=[AuthCredential(issuer=issuer.classic_address,
                                            credential_type=CRED_TYPE)]),
     recipient, "DepositPreauth(credentials)")

print("\n6a) NEGATIVE: alice -> Payment WITHOUT credential (should be blocked)")
_, code_blocked = send(Payment(account=alice.classic_address,
     destination=recipient.classic_address, amount=xrp_to_drops(1)),
     alice, "Payment (no credential)", allow_fail=True)

print("6b) POSITIVE: alice -> Payment WITH credential_ids (should pass the gate)")
res_ok, code_ok = send(Payment(account=alice.classic_address,
     destination=recipient.classic_address, amount=xrp_to_drops(1),
     credential_ids=[cred_id]), alice, "Payment (credential_ids)", allow_fail=True)

print("\n=== RESULT ===")
print(f"blocked-without-credential : {code_blocked}  (expect tecNO_PERMISSION)")
print(f"passed-with-credential     : {code_ok}  (expect tesSUCCESS)")
print(f"settlement tx hash         : {res_ok.get('hash')}")
print(f"explorer                   : https://devnet.xrpl.org/transactions/{res_ok.get('hash')}")
ok = code_blocked == "tecNO_PERMISSION" and code_ok == "tesSUCCESS"
print("\nCHAIN PROVEN ✅" if ok else "\nCHAIN NOT AS EXPECTED ❌")
