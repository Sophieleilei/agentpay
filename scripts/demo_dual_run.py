"""The signature demo over HTTP: one agent, two tasks, against the running
SafetyGate service. The blocked attempt never touches the ledger.

Self-contained — starts the gate in-process, then calls it as any external
agent would.

    python scripts/demo_dual_run.py
"""
from __future__ import annotations

import pathlib
import sys
import threading
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from src.agent.caller import call_gate, load_caller, plan  # noqa: E402
from src.config import Settings  # noqa: E402
from src.xrpl.client import balance_xrp, get_client  # noqa: E402

PORT = 8000
BASE = f"http://127.0.0.1:{PORT}"
MARK = {"pass": "✔", "fail": "✘", "hold": "⏸"}
PREMIUM = "Acquire the premium market-data bundle from vendor X."
STANDARD = "Acquire the standard market-data bundle from vendor X."


def start_gate() -> None:
    config = uvicorn.Config("src.service.app:app", host="127.0.0.1", port=PORT,
                            log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(60):
        try:
            if httpx.get(f"{BASE}/healthz", timeout=2).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.25)
    raise SystemExit("SafetyGate service did not come up")


def render(result: dict) -> None:
    body = result["body"]
    challenge = result.get("challenge")
    if challenge:
        acc = challenge["accepts"][0]
        print(f"  x402 402 → present credential {acc['credential_type']} and pay "
              f"{acc['amount_rlusd']} RLUSD to {acc['pay_to']}")
    for e in body.get("audit_trail", []):
        print(f"  {MARK.get(e['status'], '?')} {e['gate']:9} {e['reason']}")
    print(f"  → HTTP {result['status']} · {str(body.get('decision', '')).upper()}")
    if body.get("reject_reason"):
        print(f"    reason  : {body['reject_reason']}")
    if body.get("tx_hash"):
        print(f"    on-chain: {body['explorer_url']}")
    else:
        print("    on-chain: NONE — nothing settled, zero ledger footprint")


def run(label: str, task: str, wallet, recipient: str) -> None:
    print("\n" + "=" * 68)
    print(f"{label}  task: {task!r}")
    print("=" * 68)
    draft = plan(task)
    print(f"agent decided: {draft.amount} RLUSD · {draft.purpose}  ({draft.reasoning})\n")
    render(call_gate(BASE, wallet, recipient, draft))


def main() -> None:
    print(f"starting SafetyGate at {BASE} ...")
    start_gate()
    wallet, recipient = load_caller()
    client = get_client(Settings().json_rpc)

    before = balance_xrp(client, wallet.address)
    run("RUN 1", PREMIUM, wallet, recipient)
    after = balance_xrp(client, wallet.address)
    print(f"\n  zero-footprint proof: agent balance {before} → {after} "
          f"(delta {round(after - before, 6)})")

    run("RUN 2", STANDARD, wallet, recipient)

    print("\n" + "=" * 68)
    print("RUN 1 was refused at the gate (HTTP 403) before settlement — no ledger")
    print("footprint. RUN 2 cleared every gate and settled on-chain (HTTP 200).")
    print("Compliance as a precondition, enforced over a plain HTTP/x402 call.")
    print("=" * 68)


if __name__ == "__main__":
    main()
