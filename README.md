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
│  EXTERNAL AI AGENT   (any runtime — SafetyGate ships none)    │
│  Decides WHEN / TO WHOM / HOW MUCH to pay, signs a            │  ← AI lives here, OUTSIDE
│  PaymentIntent with its DID key, POSTs it over HTTP / x402.   │
└───────────────────────────┬──────────────────────────────────┘
                            │  POST /intent  (signed)
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  SafetyGate SERVICE   (100% deterministic, ZERO LLM)         │
│  intake → KYA → policy → sanctions → settle                  │  ← no AI anywhere in here
│  HTTP 402 challenge → 200 settled · 403 rejected · 202 held  │
└──────────────────────────────────────────────────────────────┘
```

**SafetyGate contains zero LLM calls** — the agent's model lives entirely on the caller's side. A safety gate must be deterministic: same input → same output, always. That is what makes it auditable, replayable, and immune to prompt injection. The agent's job is *autonomy of intent*; SafetyGate's job is *deterministic enforcement of boundaries*. That boundary is the product, and it's reachable by any agent over a plain HTTP call.

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
│   ├── service/               # the HTTP gate an external agent calls
│   │   ├── app.py             # FastAPI: POST /intent (x402), /policy, /healthz
│   │   └── context.py         # builds pipeline deps from provisioned state
│   ├── agent/                 # a DETERMINISTIC demo caller (no LLM) — stands in
│   │   ├── caller.py          # plan intent → x402 two-phase HTTP call → verdict
│   │   └── tools.py           # IntentDraft (what a caller decides)
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
- An XRPL **Devnet** endpoint with the Credentials and Permissioned Domains amendments enabled (confirmed live on Devnet and Testnet)
- No LLM or API key required — SafetyGate is pure deterministic infrastructure

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
XRPL_JSON_RPC=https://s.devnet.rippletest.net:51234
XRP_PER_RLUSD=0.001             # symbolic on-chain settlement scale (see notes)
RLUSD_ISSUER=                   # optional: settle in a real RLUSD IOU instead of XRP
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

### 4. Start the gate, then call it as an agent would

```bash
# terminal 1 — run the SafetyGate service
python -m src.service                       # serves on http://127.0.0.1:8000

# terminal 2 — an external agent submits an intent over HTTP/x402
python -m src.agent.caller --task "Pay vendor X 3000 RLUSD for the standard data bundle"
```

Expected: HTTP `402` challenge → agent signs → five green gates → `200` with an
on-chain `tx_hash` + explorer link. An over-limit task instead returns `403`
with the reject reason and **no on-chain transaction**.

The gate also exposes `GET /policy` (the rules it enforces) and `GET /healthz`.

### 5. Run the showcase (blocked → cleared)

```bash
python scripts/demo_dual_run.py             # self-contained: starts the gate, then calls it twice
```

Expected output:

```
RUN 1  task: 'Acquire the premium market-data bundle from vendor X.'
  x402 402 → present credential KYA_TIER1 and pay 8000.0 RLUSD to <recipient>
  ✔ intake    identity verified via DID
  ✔ kya       credential matched permissioned domain
  ✘ policy    amount 8000.0 exceeds per-tx limit 5000.0
  → HTTP 403 · REJECTED
    on-chain: NONE — nothing settled, zero ledger footprint
  zero-footprint proof: agent balance 90.99 → 90.99 (delta 0.0)

RUN 2  task: 'Acquire the standard market-data bundle from vendor X.'
  x402 402 → present credential KYA_TIER1 and pay 3000.0 RLUSD to <recipient>
  ✔ intake    identity verified via DID
  ✔ kya       credential matched permissioned domain
  ✔ policy    within limits, jurisdiction & purpose allowed
  ✔ sanctions counterparty cleared
  ✔ settle    x402 settled · RLUSD transferred
  → HTTP 200 · APPROVED
    on-chain: https://devnet.xrpl.org/transactions/<hash>
```

---

## The caller boundary (no LLM, by design)

SafetyGate ships **no agent and no LLM**. Whatever decides *what* to pay lives
entirely on the caller's side and reaches the gate over HTTP. The bundled
`src/agent/caller.py` is a deterministic stand-in so the demo runs with zero
external dependencies; a real LLM agent would replace it without touching the
gate.

Two properties make the boundary clean:

- **Verification is keyless.** The intake gate verifies the intent's signature
  against the agent's *on-chain DID*, not against any key the service holds — so
  the gate authenticates callers it has never met.
- **The agent's reasoning never enters the decision.** SafetyGate sees only a
  signed intent. Same intent in → same verdict out, every time. A prompt-injected
  or buggy agent still cannot talk its way past a deterministic rule.

---

## What maps to the pillar

| Pillar requirement | How SafetyGate satisfies it |
|---|---|
| On-chain tx executed **autonomously by an agent** | The agent (any runtime) signs its intent and calls the gate over HTTP/x402; settlement fires without a human in the loop |
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
- **Interface: HTTP / x402 service** (FastAPI). An external agent POSTs a signed
  intent to `/intent`; a 402 challenge returns the payment requirements, the
  signed resubmit returns the verdict (200/403/202). **Zero LLM** — the whole
  pipeline is plain deterministic Python; the bundled caller is a deterministic
  stand-in, removable without touching the gate.
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
