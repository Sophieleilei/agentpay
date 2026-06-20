"""Gate 3 — policy. Declarative spending controls, zero LLM.

Per-tx limit, daily velocity, jurisdiction allow/block, purpose allow-list, and
an approval threshold that routes to *hold* rather than reject. Same input →
same output, always.
"""
from __future__ import annotations

from datetime import datetime, timezone

from ...models import AuditEntry
from ..deps import Deps
from ..state import PipelineState

GATE = "policy"


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def run(state: PipelineState, deps: Deps) -> AuditEntry:
    intent = state.intent
    p = deps.policy

    if intent.jurisdiction in p.blocked_jurisdictions:
        return AuditEntry(gate=GATE, status="fail",
                          reason=f"jurisdiction {intent.jurisdiction} is blocked")
    if intent.jurisdiction not in p.allowed_jurisdictions:
        return AuditEntry(gate=GATE, status="fail",
                          reason=f"jurisdiction {intent.jurisdiction} is not on the allow-list")
    if intent.purpose not in p.allowed_purposes:
        return AuditEntry(gate=GATE, status="fail",
                          reason=f"purpose {intent.purpose!r} is not permitted")
    if intent.amount > p.per_tx_limit:
        return AuditEntry(gate=GATE, status="fail",
                          reason=f"amount {intent.amount} exceeds per-tx limit {p.per_tx_limit}",
                          evidence={"amount": intent.amount, "per_tx_limit": p.per_tx_limit})

    spent = deps.store.spent_today(intent.agent_address, _today())
    if spent + intent.amount > p.daily_limit:
        return AuditEntry(gate=GATE, status="fail",
                          reason=f"daily limit {p.daily_limit} would be exceeded",
                          evidence={"spent_today": spent, "amount": intent.amount})

    if intent.amount >= p.approval_threshold:
        return AuditEntry(gate=GATE, status="hold",
                          reason=f"amount {intent.amount} at/above approval threshold "
                                 f"{p.approval_threshold} — needs human sign-off",
                          evidence={"amount": intent.amount,
                                    "approval_threshold": p.approval_threshold})

    return AuditEntry(gate=GATE, status="pass",
                      reason="within limits, jurisdiction & purpose allowed",
                      evidence={"amount": intent.amount, "spent_today": spent})
