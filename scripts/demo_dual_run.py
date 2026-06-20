"""The signature demo: one agent, two tasks. It produces a blocked payment and
a cleared one on its own — and the blocked one never touches the ledger.

    python scripts/demo_dual_run.py
"""
from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.agent.runner import build_context, plan_payment  # noqa: E402
from src.agent.tools import build_intent  # noqa: E402
from src.audit.trail import render  # noqa: E402
from src.pipeline.graph import run_pipeline  # noqa: E402
from src.xrpl.client import balance_xrp  # noqa: E402

PREMIUM = "Acquire the premium market-data bundle from vendor X."
STANDARD = "Acquire the standard market-data bundle from vendor X."


def run(label: str, task: str, deps, recipient) -> None:
    print("\n" + "=" * 68)
    print(f"{label}  task: {task!r}")
    print("=" * 68)
    draft = plan_payment(task, deps.settings)
    print(f"agent decided: {draft.amount} RLUSD · {draft.purpose}  ({draft.reasoning})\n")
    intent = build_intent(draft, deps.agent_wallet, recipient)
    state = run_pipeline(intent, deps)
    print(render(state))


def main() -> None:
    deps, recipient = build_context()
    agent_addr = deps.agent_wallet.address

    before = balance_xrp(deps.client, agent_addr)
    run("RUN 1", PREMIUM, deps, recipient)
    after = balance_xrp(deps.client, agent_addr)

    print("\n--- proof of zero on-chain footprint (RUN 1) ---")
    print(f"agent XRP balance before : {before}")
    print(f"agent XRP balance after  : {after}")
    print(f"delta                    : {round(after - before, 6)}  "
          f"({'unchanged — nothing settled ✅' if before == after else 'CHANGED ❌'})")

    run("RUN 2", STANDARD, deps, recipient)

    print("\n" + "=" * 68)
    print("The transaction that did NOT happen is the hero: RUN 1 was stopped")
    print("before settlement — no ledger footprint. RUN 2 cleared every gate and")
    print("settled on-chain. Compliance as a precondition, not cleanup.")
    print("=" * 68)


if __name__ == "__main__":
    main()
