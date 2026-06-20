"""Environment settings, declarative policy, and a small local state store.

The state store (`state.json`, gitignored) is the demo's off-chain memory:
wallet seeds written by the setup scripts, plus the credential/domain/DID ids
they create on-chain. Everything compliance-critical is still verified live
against the ledger — the store only remembers *where to look*.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from dotenv import load_dotenv

from .models import Policy

load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "state.json"
POLICY_PATH = ROOT / "config" / "policy.json"


def _env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


class Settings:
    def __init__(self) -> None:
        self.json_rpc = _env("XRPL_JSON_RPC", "https://s.devnet.rippletest.net:51234")
        self.ws_endpoint = _env("XRPL_ENDPOINT", "wss://s.devnet.rippletest.net:51233")
        self.llm_provider = (_env("LLM_PROVIDER", "none") or "none").lower()
        self.llm_api_key = _env("LLM_API_KEY")
        self.llm_model = _env("LLM_MODEL", "claude-sonnet-4-6")
        self.xrp_per_rlusd = float(_env("XRP_PER_RLUSD", "0.001"))
        self.rlusd_issuer = _env("RLUSD_ISSUER")
        self.explorer = "https://devnet.xrpl.org"

    def seed(self, role: str) -> str | None:
        return _env(f"{role.upper()}_SEED")


def load_policy() -> Policy:
    return Policy(**json.loads(POLICY_PATH.read_text()))


class StateStore:
    """Tiny JSON-file store. Single-process, lock-guarded."""

    _lock = threading.Lock()

    def __init__(self, path: Path = STATE_PATH) -> None:
        self.path = path

    def _read(self) -> dict:
        if not self.path.exists():
            return {"accounts": {}, "credentials": [], "domains": {}, "dids": {}, "spend": {}}
        return json.loads(self.path.read_text())

    def _write(self, data: dict) -> None:
        self.path.write_text(json.dumps(data, indent=2))

    # --- accounts ---
    def set_account(self, role: str, address: str, seed: str, public_key: str) -> None:
        with self._lock:
            data = self._read()
            data["accounts"][role] = {
                "address": address, "seed": seed, "public_key": public_key
            }
            self._write(data)

    def account(self, role: str) -> dict | None:
        return self._read()["accounts"].get(role)

    # --- domains / credentials / dids (cached ids; verified on-chain) ---
    def set_domain(self, owner: str, domain_id: str, accepted: list[dict]) -> None:
        with self._lock:
            data = self._read()
            data["domains"][owner] = {"domain_id": domain_id, "accepted": accepted}
            self._write(data)

    def domain(self, owner: str) -> dict | None:
        return self._read()["domains"].get(owner)

    def add_credential(self, record: dict) -> None:
        with self._lock:
            data = self._read()
            data["credentials"].append(record)
            self._write(data)

    def credentials(self) -> list[dict]:
        return self._read()["credentials"]

    def set_did(self, address: str, public_key: str) -> None:
        with self._lock:
            data = self._read()
            data["dids"][address] = public_key
            self._write(data)

    # --- daily spend velocity ---
    def record_spend(self, agent: str, day: str, amount: float) -> None:
        with self._lock:
            data = self._read()
            key = f"{agent}:{day}"
            data["spend"][key] = round(data["spend"].get(key, 0.0) + amount, 2)
            self._write(data)

    def spent_today(self, agent: str, day: str) -> float:
        return self._read()["spend"].get(f"{agent}:{day}", 0.0)
