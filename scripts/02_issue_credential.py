"""Issue the KYA credential to the agent and have the agent accept it, then
verify it on-chain — proving the heart of the service has real data to read.

    python scripts/02_issue_credential.py
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Settings, StateStore  # noqa: E402
from src.xrpl.client import get_client, load_wallet  # noqa: E402
from src.xrpl.credentials import accept_credential, issue_credential, verify_credential  # noqa: E402


def main() -> None:
    settings = Settings()
    store = StateStore()
    client = get_client(settings.json_rpc)

    agent = store.account("agent")
    issuer = store.account("issuer")
    if not (agent and issuer):
        raise SystemExit("run scripts/00_setup_accounts.py first")

    issuer_wallet = load_wallet(settings.seed("issuer") or issuer["seed"])
    agent_wallet = load_wallet(settings.seed("agent") or agent["seed"])

    print(f"issuer {issuer_wallet.address} -> CredentialCreate(subject={agent_wallet.address})")
    issue_credential(client, issuer_wallet, agent_wallet.address)
    print(f"agent  {agent_wallet.address} -> CredentialAccept")
    accept_credential(client, agent_wallet, issuer_wallet.address)

    status = verify_credential(client, agent_wallet.address, issuer_wallet.address)
    print("\nverify_credential:")
    print(f"  found    : {status.found}")
    print(f"  accepted : {status.accepted}")
    print(f"  expired  : {status.expired}")
    print(f"  valid    : {status.valid}")
    print(f"  cred id  : {status.credential_id}")
    if not status.valid:
        raise SystemExit("credential did not verify — fix before running the demo")
    store.add_credential({"subject": agent_wallet.address, "issuer": issuer_wallet.address,
                          "credential_id": status.credential_id})
    print("\nprovisioning complete. run: python scripts/demo_dual_run.py")


if __name__ == "__main__":
    main()
