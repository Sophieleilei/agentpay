# SafetyGate

**Compliance-gated settlement infrastructure for autonomous AI agents.**
Built for SwissHacks 2026 — *Ripple track · Agent Financial Infrastructure.*

> An AI agent decides **what** to pay. SafetyGate decides **whether it's allowed to** — deterministically, on-chain, *before* a single token moves.

---

## The one-line pitch

When an autonomous agent wants to spend money, the dangerous moment is the gap between *"I intend to pay"* and *"the payment settled."* Today that gap is filled by trust, or by after-the-fact recovery (chargebacks, clawbacks, underwriting). SafetyGate closes the gap with a **deterministic, auditable pre-settlement gate** built on XRPL-native primitives: a bad payment never reaches the ledger in the first place.

---

## Business story

### The problem

Enterprises are starting to deploy AI agents that act on their behalf — buying data, paying for compute, settling invoices, transacting with other agents. The moment an agent can move money autonomously, the enterprise inherits a new class of risk:

- **No identity.** Is the entity initiating this payment really *our* agent, or something impersonating it?
- **No boundaries.** What stops an agent — buggy, jailbroken, or prompt-injected — from sending $80,000 when its mandate was $5,000?
- **No compliance.** Did anyone screen the counterparty for sanctions? Is this jurisdiction even allowed?
- **No audit trail.** When the regulator asks *"why did this payment happen?"*, is there an answer?

The current market answers this **after** the money moves: off-chain underwriting, risk scoring, and chargeback-style recovery once something goes wrong. That model was built for a world where reversing a transaction is possible and humans are in the loop. Autonomous agents settling on a fast, final ledger break both assumptions.

### The insight

On the XRP Ledger, **compliance can be a precondition of settlement, not a cleanup afterward.** XRPL ships native primitives — Credentials (XLS-70), Permissioned Domains (XLS-80), Decentralized Identifiers (XLS-40), and Deposit Authorization — that let the ledger itself refuse a non-compliant payment. SafetyGate wraps these into an enforcement layer that sits between an agent's intent and the settled transaction.

### What SafetyGate is

A **pre-settlement compliance gate** for agent payments. An autonomous AI agent produces a payment *intent*; SafetyGate runs that intent through a chain of deterministic checks — identity, spending policy, sanctions — and **only a fully-cleared intent ever becomes an on-chain RLUSD settlement** via the x402 flow. Everything else is rejected or escalated, with a complete audit trail, and **zero on-chain footprint for the rejected attempt.**

### Why we win this differently

| | Off-chain underwriting (e.g. t54-style) | **SafetyGate** |
|---|---|---|
| When compliance happens | After / around settlement | **Before settlement (pre-flight)** |
| Bad-transaction handling | Settle, then recover (chargeback) | **Never settles — no ledger footprint** |
| Identity model | Off-chain KYC of the operator | **On-chain KYA of the agent (DID + Credentials)** |
| Trust anchor | Underwriter's books | **XRPL ledger state + cryptographic proof** |
| Auditability | Provider's internal logs | **Deterministic, replayable decision trail** |

Where AP2 / Agent Payment Protocol (Google / FIDO) standardizes the *authorization* layer and x402 (Coinbase) standardizes the *settlement handshake*, **SafetyGate is the compliance brain in between** — and it enforces using the ledger's own native gating instead of an off-chain rulebook.

---

## Where the AI is (and where it deliberately isn't)

This pillar is about *infrastructure agents need*, **not about building AI**. SafetyGate respects that line precisely:

```
┌──────────────────────────────────────────────────────────────┐
│  AI AGENT  (LLM-driven, Pydantic AI)                          │
│  Given a task, autonomously decides WHEN / TO WHOM / HOW MUCH │  ← AI lives here
│  to pay, constructs a signed PaymentIntent, hands it off.     │
└───────────────────────────┬──────────────────────────────────┘
                            │  intent (signed)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  COMPLIANCE PIPELINE  (100% deterministic, auditable)        │
│  intake → KYA → policy → sanctions → settle                  │  ← NO AI in the decision path
│  (LLM appears ONLY to phrase rejection reasons & fuzzy-match  │
│   sanctions candidates — never to make the pass/fail call.)   │
└──────────────────────────────────────────────────────────────┘
```

**The compliance decision contains zero LLM calls.** Same input → same output, always. That is what makes it auditable, replayable, and immune to prompt injection. The AI's job is *autonomy of intent*; the infrastructure's job is *deterministic enforcement of boundaries*. That boundary is the product.

---

## Architecture

### The four gates

A deterministic, hand-written pipeline (no graph framework — the compliance path stays plain, auditable Python). Any gate that fails routes straight to a terminal `reject` state — **the only path to `settle` is all gates passing.** Safety is topological: you cannot reach settle without traversing every prior gate.

```
agent intent
     │
  ┌──▼─────┐   sig invalid ──────────────┐
  │ intake │   (DID pubkey verify)        │
  └──┬─────┘                              │
  ┌──▼─────┐   no valid credential ───────┤
  │  KYA   │   (XLS-70 + XLS-80 match)     │
  └──┬─────┘                              │
  ┌──▼─────┐   limit / jurisdiction ──────┤
  │ policy │   (or → hold for approval)    ├──► reject  (no on-chain tx)
  └──┬─────┘                              │
  ┌──▼─────┐   sanctions hit ─────────────┤
  │sanction│                              │
  └──┬─────┘                              │
  ┌──▼─────┐                              │
  │ settle │ ──► x402 handshake + RLUSD ──► on-chain ✅
  └────────┘
     │
  audit_trail accumulates one entry per gate (pass/fail/reason/evidence)
```

| Gate | Checks | XRPL primitive | AI? |
|---|---|---|---|
| **intake** | Agent signature matches DID public key (binds this request to the on-chain account) | XLS-40 DID | no |
| **KYA** | Agent holds a valid credential: exists + accepted + not expired + matches recipient's permissioned domain | XLS-70 Credentials, XLS-80 Domains | no |
| **policy** | Per-tx limit · daily velocity · jurisdiction allow/block · purpose · approval threshold → may **hold** instead of reject | declarative config | no |
| **sanctions** | Counterparty screened against sanction lists (fuzzy-match candidates may use LLM; threshold is deterministic) | mock OFAC-style list | optional, non-deciding |
| **settle** | x402 402-handshake, then RLUSD `Payment` carrying the credential ID through the on-chain gate | x402 + RLUSD + Deposit Auth | no |

### State (Pydantic)

```python
class PipelineState(BaseModel):
    intent: PaymentIntent                  # recipient, amount, jurisdiction, purpose, signature, nonce
    audit_trail: list[AuditEntry]          # one entry appended per gate
    decision: Literal["pending", "approved", "rejected", "held"]
    reject_reason: str
    credential_id: str | None              # found by KYA, presented on-chain by settle
    tx_hash: str | None
    explorer_url: str | None
```

### Three roles

```
A = recipient / authorizer  → configures the permissioned domain + deposit auth
B = the AI agent (payer)    → autonomously produces & signs intents
I = credential issuer        → vets B off-chain, issues the KYA credential on-chain
```

---

## The demo: an agent that hits the wall, reads why, and self-corrects

The signature moment. One agent, two tasks — it produces both a blocked and a cleared payment **on its own**.

```
TASK 1  "Acquire the premium market-data bundle from vendor X."
  → agent reasons: needs vendor X, price 8,000 RLUSD
  → constructs intent (8,000)
  → policy gate: 8,000 > 5,000 per-tx limit → REJECT
  → ZERO on-chain tx. RLUSD balance unchanged. audit_trail logs why.
  → agent reads the rejection reason → re-plans

TASK 1'  agent self-corrects: splits / downgrades to the 3,000 standard bundle
  → all four gates pass → x402 + RLUSD settle on-chain
  → explorer link + full green audit trail
```

**The 30-second judge script:**

> "Same agent, same goal. First it tries to spend 8,000 — over the institutional limit. Our pre-settlement gate stops it *before* settlement: **zero on-chain transaction, not a single token moved**, and the audit trail records exactly which rule fired. The agent reads that reason and adjusts. The second attempt is compliant — gates clear, x402 + RLUSD settle.
>
> Other approaches let the transaction land and recover afterward. **SafetyGate is XRPL-native pre-settlement gating — the bad payment never reaches the ledger.** Compliance isn't cleanup. It's a precondition of settlement."

The **transaction that did not happen** is the hero of this demo.

---

## Repository layout

```
safetygate/
├── README.md
├── requirements.txt
├── pyproject.toml
├── .env.example
├── config/
│   ├── policy.json            # declarative spending policy (edit without touching code)
│   └── sanctions.json         # mock OFAC-style list
├── src/
│   ├── config.py              # env settings + local state store (state.json)
│   ├── models.py              # PaymentIntent, AuditEntry, Policy (Pydantic)
│   ├── agent/
│   │   ├── runner.py          # Pydantic AI agent: task → intent (deterministic fallback)
│   │   └── tools.py           # IntentDraft + sign/build intent
│   ├── pipeline/
│   │   ├── graph.py           # deterministic gate runner + fail-closed routing
│   │   ├── state.py           # PipelineState (Pydantic)
│   │   ├── deps.py            # what the gates read from
│   │   └── nodes/
│   │       ├── intake.py      # DID signature verification
│   │       ├── kya.py         # credential + permissioned-domain check
│   │       ├── policy.py      # spending controls (3-state: approve/reject/hold)
│   │       ├── sanctions.py   # counterparty screening
│   │       └── settle.py      # x402 handshake + on-chain settlement
│   ├── xrpl/
│   │   ├── client.py          # client, wallets, submit, CredentialIDs codec shim
│   │   ├── credentials.py     # CredentialCreate / Accept / verify (the heart)
│   │   ├── domains.py         # PermissionedDomainSet + DepositPreauth
│   │   ├── did.py             # DIDSet + resolve public key
│   │   └── settlement.py      # x402 handshake + Payment(CredentialIDs)
│   └── audit/
│       └── trail.py           # render decision chain (CLI + JSON)
├── scripts/
│   ├── 00_setup_accounts.py   # fund agent / recipient / issuer; publish agent DID
│   ├── 01_setup_domain.py     # recipient: domain + deposit auth + preauth
│   ├── 02_issue_credential.py # issuer issues, agent accepts, verify on-chain
│   └── demo_dual_run.py       # the blocked-then-cleared showcase
└── validate_chain.py          # one-shot Devnet proof of the whole primitive chain
```

---

## Executable steps

### Prerequisites

- Python 3.11+
- An XRPL **Testnet** (Devnet) endpoint with the Credentials and Permissioned Domains amendments enabled
- An Anthropic / Groq API key for the LLM agent (the agent layer is optional and degrades gracefully)

### 1. Install

```bash
git clone <your-repo-url> safetygate
cd safetygate
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
```

Fill in `.env`:

```dotenv
XRPL_ENDPOINT=wss://s.devnet.rippletest.net:51233
LLM_PROVIDER=anthropic          # or "groq"
LLM_API_KEY=sk-...
LLM_MODEL=claude-sonnet-4-6
RLUSD_ISSUER=r...               # RLUSD issuer address on your test network
# Wallet seeds are generated by step 3 and written back here.
```

Edit `config/policy.json` to taste:

```json
{
  "per_tx_limit": 5000,
  "daily_limit": 20000,
  "approval_threshold": 10000,
  "allowed_jurisdictions": ["CH", "EU", "US"],
  "blocked_jurisdictions": ["IR", "KP"],
  "allowed_purposes": ["settlement", "data_purchase", "compute"]
}
```

> The policy is **declarative config, not hard-coded logic** — a risk team adjusts an agent's authority by editing JSON, never the pipeline.

### 3. Provision accounts (one-time)

```bash
python scripts/00_setup_accounts.py    # funds A (recipient), B (agent), I (issuer); writes seeds to .env
python scripts/01_setup_domain.py      # A: PermissionedDomainSet + AccountSet(asfDepositAuth) + DepositPreauth
python scripts/02_issue_credential.py  # I: CredentialCreate(Subject=B);  B: CredentialAccept
```

After this, B holds a valid, accepted KYA credential that matches A's permissioned domain.

### 4. Run a single intent through the gate

```bash
python -m src.agent.runner --task "Pay vendor X 3000 RLUSD for the standard data bundle"
```

Expected: four green gates → x402 settle → on-chain `tx_hash` + explorer link + audit trail.

### 5. Run the showcase (blocked → cleared)

```bash
python scripts/demo_dual_run.py
```

Expected output:

```
RUN 1  task: "acquire premium market-data bundle"
  intent: 8000 RLUSD → vendor X
  ✔ intake     identity verified via DID
  ✔ kya        credential matched permissioned domain
  ✘ policy     amount 8000 > per-tx limit 5000   → REJECTED
  -- settle skipped. on-chain tx: NONE. RLUSD moved: 0.00
  agent re-plans...

RUN 2  task (self-corrected): "acquire standard market-data bundle"
  intent: 3000 RLUSD → vendor X
  ✔ intake     identity verified via DID
  ✔ kya        credential matched permissioned domain
  ✔ policy     within limits, jurisdiction & purpose allowed
  ✔ sanctions  counterparty cleared
  ✔ settle     x402 settled · RLUSD transferred
  tx: https://devnet.xrpl.org/transactions/<hash>
```

### 6. (Optional) Audit-trail UI

```bash
cd ui && npm install && npm run dev
```

A timeline view of every gate's pass/fail/reason — red where a run stopped, green where it cleared. This is the visual that sells the "guardrails with teeth" story.

---

## The autonomous layer (option C), with graceful degradation

The agent is the source of *autonomy*, but it is **never on the critical compliance path** and is **fully removable**:

```python
def produce_intent(task: str) -> PaymentIntent:
    try:
        return llm_agent.plan_payment(task)   # LLM decides recipient / amount / purpose
    except Exception:
        return FALLBACK_INTENTS[task]          # hard-coded intent if the LLM is unavailable
```

If the LLM provider is down mid-demo, the pipeline still runs on a deterministic fallback intent — the core infrastructure never depends on the AI. The AI buys you the "agent hit the wall and self-corrected" narrative; it does not put the demo at risk.

---

## What maps to the pillar

| Pillar requirement | How SafetyGate satisfies it |
|---|---|
| On-chain tx executed **autonomously by an agent** | LLM agent constructs & signs the intent; settlement fires without a human in the loop |
| **Compliance checks** | KYA (DID + Credentials + Permissioned Domains) + sanctions screening |
| **Policy enforcement** | Declarative spending policy: limits, approval thresholds, jurisdiction restrictions |
| **Spending limits / approval thresholds** | 3-state policy gate (approve / reject / **hold for approval**) |
| **Audit trails** | Accumulating, replayable decision chain rendered per run |
| **RLUSD settlement in an x402 flow** | settle node: x402 402-handshake → RLUSD `Payment` carrying the credential ID through the on-chain gate |

Covers example angles ① KYA, ② Spending Policies, and ③ Regulated Settlement in a single pipeline.

---

## Implementation notes (what's actually wired & tested)

- **Network: XRPL Devnet.** The Credentials, PermissionedDomains, DepositPreauth
  and DID amendments are all confirmed enabled there (and on Testnet). Run
  `python validate_chain.py` to re-prove the full primitive chain end-to-end.
- **Agent layer: Pydantic AI**, not LangGraph. The compliance pipeline itself is
  plain deterministic Python — no framework on the decision path.
- **Settlement currency.** The on-chain settlement is a native **XRP** Payment
  carrying `CredentialIDs`, an `InvoiceID`, and a memo recording the true RLUSD
  amount. XRP keeps the gating logic provable today within faucet balances;
  swapping to an RLUSD IOU (set `RLUSD_ISSUER` + trustlines) is a currency change
  only — the gate logic is currency-agnostic.
- **The on-chain gate is real.** A payment *without* the credential is rejected by
  the ledger with `tecNO_PERMISSION`; *with* `CredentialIDs` it clears. Proven.
- **xrpl-py 5.0.0 shim.** That version mis-cases `credential_ids` → `CredentialIds`
  (ledger field is `CredentialIDs`), which breaks signing. `src/xrpl/client.py`
  installs a one-line abbreviation fix on import.

## Glossary

- **KYA — Know Your Agent.** Identity verification for an agent (the agent analog of KYC), here via on-chain DID + Credentials.
- **x402.** HTTP 402-based payment handshake layer (Coinbase-led).
- **AP2 / Agent Payment Protocol.** Authorization-layer standard (Google-led, FIDO-governed) — complementary to, not competing with, SafetyGate's compliance layer.
- **RLUSD.** Ripple USD stablecoin used for settlement.
- **Pre-settlement gating.** Enforcing compliance *before* a transaction reaches the ledger, so non-compliant payments leave no on-chain footprint.

---

*SwissHacks 2026 · Zurich · June 19–21 · Ripple track — Agent Financial Infrastructure.*
