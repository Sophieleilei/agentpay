"""The autonomous agent layer (Pydantic AI) + the wiring that runs an intent
through the compliance pipeline.

The AI is the source of *autonomy of intent* and nothing more — it is never on
the compliance decision path and degrades to a deterministic fallback if the
LLM is unavailable, so the demo never depends on a model being up.

    python -m src.agent.runner --task "Pay vendor X 3000 RLUSD for the data bundle"
"""
from __future__ import annotations

import argparse
import json
import os
import re

from ..audit.trail import render, to_json
from ..config import ROOT, Settings, StateStore, load_policy
from ..pipeline.deps import Deps
from ..pipeline.graph import run_pipeline
from ..xrpl.client import get_client, load_wallet
from .tools import IntentDraft, build_intent

SYSTEM_PROMPT = (
    "You are an autonomous procurement agent for an enterprise. Given a task, "
    "decide how much to pay in RLUSD, the purpose (one of: settlement, "
    "data_purchase, compute), and the counterparty jurisdiction (ISO-3166 "
    "alpha-2, e.g. CH). Be realistic about institutional prices."
)


def plan_payment(task: str, settings: Settings) -> IntentDraft:
    """LLM decides the intent; falls back to a deterministic draft on any error."""
    if settings.llm_provider == "anthropic" and settings.llm_api_key:
        try:
            from pydantic_ai import Agent

            os.environ.setdefault("ANTHROPIC_API_KEY", settings.llm_api_key)
            agent = Agent(f"anthropic:{settings.llm_model}",
                          output_type=IntentDraft, system_prompt=SYSTEM_PROMPT)
            return agent.run_sync(task).output
        except Exception as exc:  # noqa: BLE001 - LLM is optional, never fatal
            print(f"[agent] LLM unavailable ({exc}); using deterministic fallback")
    return _fallback(task)


def _fallback(task: str) -> IntentDraft:
    t = task.lower()
    match = re.search(r"(\d[\d,]*)", t)
    if match:
        amount = float(match.group(1).replace(",", ""))
    else:
        amount = 8000.0 if "premium" in t else 3000.0
    if "compute" in t:
        purpose = "compute"
    elif "data" in t or "bundle" in t:
        purpose = "data_purchase"
    else:
        purpose = "settlement"
    return IntentDraft(amount=amount, purpose=purpose, jurisdiction="CH",
                       reasoning="deterministic fallback (no LLM)")


def load_sanctions() -> frozenset[str]:
    path = ROOT / "config" / "sanctions.json"
    if path.exists():
        return frozenset(json.loads(path.read_text()).get("blocked_addresses", []))
    return frozenset()


def build_context() -> tuple[Deps, str]:
    """Assemble pipeline deps + the recipient address from provisioned state."""
    settings = Settings()
    store = StateStore()
    agent_acct = store.account("agent")
    recipient_acct = store.account("recipient")
    issuer_acct = store.account("issuer")
    if not (agent_acct and recipient_acct and issuer_acct):
        raise SystemExit("accounts not provisioned — run: python scripts/00_setup_accounts.py")

    agent_seed = settings.seed("agent") or agent_acct["seed"]
    deps = Deps(
        client=get_client(settings.json_rpc),
        settings=settings,
        policy=load_policy(),
        store=store,
        issuer_address=issuer_acct["address"],
        agent_wallet=load_wallet(agent_seed),
        sanctions=load_sanctions(),
    )
    return deps, recipient_acct["address"]


def run_task(task: str) -> None:
    deps, recipient = build_context()
    draft = plan_payment(task, deps.settings)
    print(f"[agent] intent: {draft.amount} RLUSD · {draft.purpose} · {draft.jurisdiction}"
          f"  ({draft.reasoning})\n")
    intent = build_intent(draft, deps.agent_wallet, recipient)
    state = run_pipeline(intent, deps)
    print(render(state))
    if os.environ.get("AUDIT_JSON"):
        print("\n" + to_json(state))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one agent intent through SafetyGate")
    parser.add_argument("--task", required=True, help="Natural-language payment task")
    run_task(parser.parse_args().task)


if __name__ == "__main__":
    main()
