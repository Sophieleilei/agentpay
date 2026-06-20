"""Provision the three testnet accounts (no wallet app required).

agent (Alice, payer) · recipient (merchant) · issuer (KYA authority).
Funds them from the faucet, publishes the agent's DID, and writes the seeds to
both state.json and .env so every later script and the service reuse them.

    python scripts/00_setup_accounts.py
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import Settings, StateStore  # noqa: E402
from src.xrpl.client import fund_wallet, get_client  # noqa: E402
from src.xrpl.did import set_did  # noqa: E402

ROLES = ["agent", "recipient", "issuer"]


def upsert_env(values: dict[str, str]) -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        env_path.write_text((ROOT / ".env.example").read_text())
    lines = env_path.read_text().splitlines()
    keys = set(values)
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in keys:
            out.append(f"{key}={values[key]}")
            keys.discard(key)
        else:
            out.append(line)
    for key in keys:
        out.append(f"{key}={values[key]}")
    env_path.write_text("\n".join(out) + "\n")


def main() -> None:
    settings = Settings()
    store = StateStore()
    client = get_client(settings.json_rpc)

    print(f"funding accounts on {settings.json_rpc} ...")
    env_updates: dict[str, str] = {}
    wallets = {}
    for role in ROLES:
        wallet = fund_wallet(client)
        wallets[role] = wallet
        store.set_account(role, wallet.address, wallet.seed, wallet.public_key)
        env_updates[f"{role.upper()}_SEED"] = wallet.seed
        print(f"  {role:10} {wallet.address}  seed={wallet.seed}")

    print("\npublishing the agent's DID (identity for the intake gate) ...")
    set_did(client, wallets["agent"])
    store.set_did(wallets["agent"].address, wallets["agent"].public_key)
    print("  DID published")

    upsert_env(env_updates)
    print("\nseeds written to .env and state.json")
    print("next: python scripts/01_setup_domain.py")


if __name__ == "__main__":
    main()
