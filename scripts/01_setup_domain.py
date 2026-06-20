"""Recipient-side gating: permissioned domain + deposit auth + preauth.

The merchant declares it only accepts the issuer's KYA credential. After this,
the ledger itself rejects any payment that doesn't present that credential.

    python scripts/01_setup_domain.py
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Settings, StateStore  # noqa: E402
from src.xrpl.client import get_client, load_wallet  # noqa: E402
from src.xrpl.domains import configure_recipient  # noqa: E402


def main() -> None:
    settings = Settings()
    store = StateStore()
    client = get_client(settings.json_rpc)

    recipient = store.account("recipient")
    issuer = store.account("issuer")
    if not (recipient and issuer):
        raise SystemExit("run scripts/00_setup_accounts.py first")

    recipient_wallet = load_wallet(settings.seed("recipient") or recipient["seed"])
    print(f"configuring recipient {recipient_wallet.address} to accept issuer "
          f"{issuer['address']} ...")
    result = configure_recipient(client, recipient_wallet, issuer["address"])
    store.set_domain(recipient_wallet.address, result["domain_id"],
                     [{"issuer": issuer["address"], "credential_type": result["credential_type"]}])
    print(f"  permissioned domain : {result['domain_id']}")
    print("  deposit auth        : enabled")
    print("  preauth by credential: set")
    print("\nnext: python scripts/02_issue_credential.py")


if __name__ == "__main__":
    main()
