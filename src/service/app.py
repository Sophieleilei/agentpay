"""SafetyGate HTTP service — the deterministic pre-settlement gate an external
AI agent calls. No LLM anywhere in here.

x402 two-phase flow on `POST /intent`:

  1. Agent POSTs an intent with no signature.
     → 402 Payment Required, body carries the payment requirements (accepts)
       and the exact canonical bytes to sign.
  2. Agent signs those bytes with its DID key and resubmits.
     → 200 approved + settled (tx_hash) · 403 rejected (reason) · 202 held.

A rejected intent never reaches settle, so it leaves zero on-chain footprint.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ..models import PaymentIntent
from ..pipeline.graph import run_pipeline
from ..xrpl.client import CREDENTIAL_TYPE
from .context import ServiceContext, build_context

_STATUS = {"approved": 200, "held": 202, "rejected": 403}


class IntentRequest(BaseModel):
    agent_address: str = Field(description="Payer agent's XRPL r-address")
    recipient: str = Field(description="Counterparty r-address")
    amount: float = Field(gt=0, description="Amount in RLUSD")
    purpose: str
    jurisdiction: str
    nonce: str = Field(description="Unique per-intent replay guard")
    public_key: str | None = None
    signature: str | None = None

    def to_intent(self) -> PaymentIntent:
        return PaymentIntent(
            agent_address=self.agent_address, recipient=self.recipient,
            amount=self.amount, purpose=self.purpose, jurisdiction=self.jurisdiction,
            nonce=self.nonce, public_key=self.public_key, signature=self.signature,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ctx = build_context()
    yield


app = FastAPI(title="SafetyGate",
              description="Compliance-gated pre-settlement gate for autonomous agents (XRPL).",
              version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/policy")
def policy(request: Request) -> dict:
    """Agent-discoverable: the spending policy this gate enforces."""
    ctx: ServiceContext = request.app.state.ctx
    return ctx.deps.policy.model_dump()


@app.post("/intent")
def submit_intent(req: IntentRequest, request: Request) -> JSONResponse:
    ctx: ServiceContext = request.app.state.ctx

    # Phase 1: no signature yet → answer with the x402 payment requirements
    # and the exact payload the agent must sign.
    if not req.signature or not req.public_key:
        unsigned = req.to_intent()
        return JSONResponse(status_code=402, content={
            "x402_version": 1,
            "accepts": [{
                "scheme": "xrpl-credential",
                "pay_to": req.recipient,
                "amount_rlusd": req.amount,
                "credential_type": CREDENTIAL_TYPE,
                "issuer": ctx.issuer,
            }],
            "payload_to_sign_hex": unsigned.signing_payload().hex(),
            "instructions": "sign payload_to_sign_hex with your DID key; "
                            "resubmit this body with public_key + signature",
        })

    # Phase 2: signed → run the deterministic gate.
    state = run_pipeline(req.to_intent(), ctx.deps)
    body = {
        "decision": state.decision,
        "reject_reason": state.reject_reason or None,
        "tx_hash": state.tx_hash,
        "explorer_url": state.explorer_url,
        "audit_trail": [e.model_dump() for e in state.audit_trail],
    }
    return JSONResponse(status_code=_STATUS.get(state.decision, 400), content=body)
