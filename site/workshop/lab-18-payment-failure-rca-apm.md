---
title: "Lab 18 — Root-cause a failed payment on drones.<DNS_DOMAIN> with OCI APM"
description: "A customer reports that 'completing payment' on the storefront errors out — but the checkout returns HTTP 200. Walk the OCI APM Trace Explorer path to the failing payment-gateway span, prove the trace is NOT a server fault, identify the antifraud DECLINE as the real root cause, correlate to Log Analytics by trace_id, then fix it and verify."
---

# Lab 18 — Root-cause a failed payment with OCI APM

!!! info "Lab Facts"
    - **Time:** 35 minutes
    - **Surfaces (the path you'll pivot across):** OCI APM Trace Explorer · OCI Log Analytics · (optional) the storefront RUM session
    - **Service under test:** `octo-drone-shop-oke` (FastAPI checkout) → `octo-java-app-server-oke` (Java antifraud / payment sidecar)
    - **Failing span:** `payment_gateway.credit_card.merchant_authorization_result`
    - **Prereqs:** Labs 01-03 (trace minting, trace↔log correlation, span drill-down); Lab 10 (failed-checkout pivot) and Lab 17 (APM→LogAn root-cause pivot) recommended — this lab reuses their `trace_id`-as-join-key discipline but targets the **payment rail**, not the CRM sync or the workflow-gateway DB sweep

## Objective

Learn how to root-cause a payment that *looks* broken to the user but is
not a server crash. You will drive the same path a real operator follows
when a customer says **"I tried to pay on `https://drones.<DNS_DOMAIN>` and
it errored out"**: start at the **OCI APM Trace Explorer**, drill to the
**failing payment-gateway span**, read its attributes, prove the trace is
**`is-fault=false` / `error-span-count=0`** (so it never 5xx'd), follow the
upstream Java antifraud call, and conclude that the "error" is a **designed
antifraud DECLINE** — a *business* outcome, not a *technical* fault. The
skill this lab builds is telling those two apart from the trace alone, then
carrying the `trace_id` into Log Analytics to confirm the decline reason.

## What good looks like

By the end you can state, in one sentence, **why the payment "failed", with
evidence at each layer**:

- **APM Trace Explorer** shows a `shop.checkout` trace that returned
  HTTP 200 with **49 spans, `is-fault=false`, `error-span-count=0`** — no
  server fault at all.
- The **`payment_gateway.credit_card.merchant_authorization_result`** span
  carries `payment.status = declined`,
  `payment.decision_source = java-antifraud-verification-app`,
  `payment.risk_score = 99`, and a misleading `otel.status_code = ERROR`.
- Its upstream child **`HTTP POST /api/java-apm/payment/verify`** on
  `octo-java-app-server-oke` returned **HTTP 200** with a high risk score —
  proving the decline is an antifraud *decision*, not a 5xx.
- **Log Analytics**, filtered by that same `trace_id`, shows the correlated
  "Simulated payment gateway decision" record with the decline reason.

That chain — symptom → trace → failing payment span → upstream antifraud
decision → log confirmation → fix — is the entire lab.

## The fault you'll exercise

The storefront's checkout flow is healthy end-to-end, but a **share of
checkouts are intentionally DECLINED by the antifraud tier**. On live
demo traffic, roughly **1 in 4 checkouts** declines: the Java antifraud
service (`java-antifraud-verification-app`) returns a risk score of **98-99**
for decline-test cards and the seeded "issuer decline" demo scenario, and
the gateway collapses that into `payment.status = declined`.

Critically, **the checkout HTTP request still succeeds (HTTP 200)** with
`status = order_placed`. The order is simply written as
`payment_pending / payment_required=1`, and the storefront renders
*"Order #N placed. Payment failed … Payment still required."* That string is
what the customer reports as "the payment errored out" — but there is **no
crash, no 5xx, no exception** anywhere on the path.

!!! warning "The trap this lab teaches you to avoid"
    The declined gateway spans are flagged `otel.status_code = ERROR`, yet
    the overall trace is **not** a fault (`is-fault=false`,
    `error-span-count=0`, trace-level `StatusCode` is `Unset`). So a normal
    business decline *looks* like a silent technical failure in Trace
    Explorer — and it will **not** appear under the "Errored Traces"
    quick-pick. If you only trust the red span colour, you misdiagnose a
    designed decline as a backend bug. The whole point of this lab is to
    read past that.

---

## Step 0 — Reproduce the symptom (optional)

You can run this lab against existing live traffic (the seeded decline
scenario fires on its own cadence), or deliberately reproduce a decline so
you have a fresh `trace_id` to chase.

To reproduce a decline, submit a checkout on `https://drones.<DNS_DOMAIN>`
using a **decline-test card** — the path that the seeded `oci-apm-issuer-decline-*`
sessions exercise:

```text
Card number: 4000 0000 0000 0002   (issuer-decline test PAN)
Expiry:      any future date
CVV:         any 3 digits
```

**What you see (the symptom):** the page returns *"Order #N placed. Payment
failed … Payment still required."* This is the exact wording a customer
reports as "completing the payment errors out".

??? note "Driving it headlessly"
    If you'd rather not click through the UI, POST the same payload to the
    checkout endpoint (decline-test PAN in `payment_details`):

    ```bash
    curl -sS -X POST "https://drones.<DNS_DOMAIN>/api/shop/checkout" \
      -H "Content-Type: application/json" \
      -b "octo_session=<your_session_cookie>" \
      -d '{
            "payment_method": "credit_card",
            "payment_details": {"number": "4000000000000002", "exp": "12/30", "cvv": "123"}
          }' | jq '{status, payment: .payment.status, payment_required}'
    # expect: {"status":"order_placed","payment":"declined","payment_required":true}
    ```

    Note the response is **HTTP 200** even though `payment.status` is
    `declined` — that is the whole misperception in one line.

---

## Step 1 — APM Trace Explorer: find the checkout traces

```text
OCI Console → Observability & Management → Application Performance Monitoring → Trace Explorer
```

Top-right, scope to your APM domain:

```text
Compartment = LogAnalytics
APM Domain  = octo-emdemo-apm
Time range  = Last 7 days
```

!!! tip "Why 7 days, not the default 1 hour"
    Declines are sparse demo traffic. A 1-hour window may show zero. Widen
    to last 7 days so you actually have declined traces to open.

Switch to the **query/edit** bar and list the top-level checkout spans:

```text
show spans ServiceName, OperationName where ServiceName = 'octo-drone-shop-oke' and OperationName = 'shop.checkout'
```

**What you see:** the storefront's checkout spans. Each one expands into a
49-span trace covering cart resolution, order persist, payment authorize,
the gateway emulator's per-step spans, the two Java sidecar calls, payment
state persist, and CRM sync.

!!! note "APM query syntax"
    It's `show spans <attrs> where …` with **no parentheses** after
    `spans`, **single-quoted** string literals, and dotted attributes must
    be *activated* in the domain to be queryable. See
    [Lab 01](lab-01-first-trace.md) for the attribute model.

---

## Step 2 — Filter to the final gateway decision span

The top-level `shop.checkout` span doesn't tell you the outcome — the
**final gateway decision** does. Filter to it:

```text
show spans ServiceName, OperationName where OperationName = 'payment_gateway.credit_card.merchant_authorization_result'
```

(For wallet flows, the equivalent is
`payment_gateway.google_pay.merchant_authorization_result`.)

Sort by **Start Time desc** and look for a span whose `payment.status` is
`declined`. The seeded decline traffic uses session ids like
`oci-apm-issuer-decline-*` / `*visa-declined*`. Click one and open its
**Trace** to see the full waterfall.

**What you see:** a 49-span flame chart. Three spans are flagged red /
`otel.status_code = ERROR`:

- `payment.simulated.authorize`
- `payment_gateway.credit_card.verification_antifraud_response`
- `payment_gateway.credit_card.merchant_authorization_result` ← **land here**

The last one is the **final gateway decision** — the failing span you want.

---

## Step 3 — Read the failing span's attributes

Open the **Span Attributes / Tags** panel on
`payment_gateway.credit_card.merchant_authorization_result`:

| Attribute | Value | What it tells you |
|---|---|---|
| `payment.status` | `declined` | the payment was rejected |
| `payment.decision_source` | `java-antifraud-verification-app` | **who** rejected it: the Java antifraud tier |
| `payment.risk_score` | `99` | the antifraud risk that drove it |
| `payment.error_code` | `ANTIFRAUD_DECLINED` / `ANTIFRAUD_HIGH_RISK` | the decline category |
| `payment.gateway.final` | `true` | this is the authoritative decision span |
| `otel.status_code` | `ERROR` | **misleading** — see the next step |

**Copy the `trace_id`** (32 hex chars) and the **Order ID** from the trace
header. The `trace_id` is your join key for Log Analytics in Step 6.

!!! tip "What to read first, every time"
    On any payment span: (1) `payment.status`, (2) `payment.decision_source`
    (local vs. `java-antifraud-verification-app`), (3) `payment.risk_score`
    and `payment.error_code`. Those three answer *what happened*, *who
    decided*, and *why*.

---

## Step 4 — Prove it is NOT a server fault

This is the step that separates a real operator from someone who trusts the
red span colour. Open the **trace header / trace summary** and read the
**trace-level** fields:

- `is-fault` = **`false`**
- `error-span-count` = **`0`**
- trace-level `StatusCode` = **`Unset`**
- span count = **49** (the full, intact checkout flow)

```text
show spans TraceId, OperationName, StatusCode where TraceId = '<TRACE_ID>'
```

**What you see:** every span present, the `/api/shop/checkout` endpoint
`StatusCode = Unset` (no 5xx), and zero spans contributing to a fault. The
three `otel.status_code = ERROR` payment spans are flagged at the
*span-attribute* level only — they do **not** make the trace a fault.

> **Conclusion so far:** there is no crash, timeout, or exception. The
> checkout succeeded technically (HTTP 200). The "failure" is a *decision*
> made inside the payment path, not a *fault* in it.

---

## Step 5 — Follow the decision upstream to the Java antifraud tier

Now prove **who** made the decision. In the waterfall, click the upstream
child span:

```text
HTTP POST /api/java-apm/payment/verify   (service: octo-java-app-server-oke)
```

Read its attributes:

- `http.response.status_code` = **`200`** — the antifraud tier answered
  cleanly, it did not error.
- `payment.risk_score` = **90+** — the antifraud verification returned a
  high risk score, which the gateway turned into a decline.

**What you see:** the Java antifraud service (`java-antifraud-verification-app`)
returned HTTP 200 with a high risk score. The decline is a **business /
antifraud decision**, not a 5xx. The sibling `HTTP POST
/api/java-apm/payment/authorize` span confirms the same — present, 200, no
error.

!!! note "The decision path in one breath"
    `shop.checkout` → `payment.simulated.authorize` → gateway emulator emits
    per-step `payment_gateway.credit_card.*` spans → it calls the Java
    sidecar **verify** then **authorize** (both HTTP 200) → the gateway
    merges those into one `merchant_authorization_result` and sets
    `otel.status_code = ERROR` because `status != authorized`. Decline-test
    cards (`4000000000000002`, `5105105105105100`) set the
    `issuer_decline_test_card` risk reason that pushes the score to 99.

---

## Step 6 — Correlate to Log Analytics by trace_id

Carry the `trace_id` into the logs to read the decline reason in plain
text. Every app log record is stamped with the active trace id as
`oracleApmTraceId` (the [correlation contract](../architecture/correlation-contract.md)
guarantees the trace↔log join — the same bridge you used in
[Lab 10](lab-10-failed-checkout.md) and [Lab 17](lab-17-root-cause-apm-logan.md)).

```text
OCI Console → Observability & Management → Logging Analytics → Log Explorer
```

Query (replace `<TRACE_ID>` with the value from Step 3):

```text
'Log Source' = 'OCI Unified Schema Logs'
  and oracleApmTraceId = '<TRACE_ID>'
  | sort -Time
```

**What you see:** the correlated `WARNING` record —
*"Simulated payment gateway decision"* — for that exact checkout, showing
`payment.status = declined`, the decision source, and the risk reason that
the truncated span attributes only hinted at.

You can also drive the two project-shipped saved searches by `trace_id` /
payment-gateway request id:

```bash
# Correlate the checkout + payment records for one trace
oci log-analytics query \
  --namespace-name "<LA_NAMESPACE>" \
  --compartment-id "<COMPARTMENT_OCID>" \
  --query-string "$(cat deploy/oci/log_analytics/searches/checkout-payment-correlation.sql)"

# Triage the gateway / antifraud decision detail
oci log-analytics query \
  --namespace-name "<LA_NAMESPACE>" \
  --compartment-id "<COMPARTMENT_OCID>" \
  --query-string "$(cat deploy/oci/log_analytics/searches/payment-gateway-security-triage.sql)"
```

!!! warning "It won't be under 'Errored Traces'"
    Because the trace's `is-fault` is `false` and `error-span-count` is `0`,
    it will **not** show up under Trace Explorer's default *Errored Traces*
    quick-pick. You must query by `OperationName` / `payment.status` (Step 2)
    — exactly why the red-span-colour shortcut fails here.

??? note "No trace_id field in your logs?"
    Some sources name it `trace_id` rather than `oracleApmTraceId`; try
    `... and trace_id = '<TRACE_ID>'`. Both refer to the same W3C trace id.
    In current deployments, direct/OKE app rows use `SOC Application Logs`
    and Connector-Hub rows use `OCI Unified Schema Logs`.

---

## Step 7 — Conclude root cause, fix, and verify

### Root cause (write it like this)

> A share (~28% on sampled live traffic) of checkouts on
> `https://drones.<DNS_DOMAIN>` are **DECLINED by the antifraud tier by
> design** — decline-test cards and the seeded `oci-apm-issuer-decline`
> scenario drive the Java `java-antifraud-verification-app` to a risk score
> of 98-99, so the gateway returns `payment.status = declined`. The checkout
> still returns **HTTP 200** with `payment_required=1`, which the storefront
> renders as *"Payment failed … Payment still required."* There is **no
> server fault**: every checkout trace is `is-fault=false` with
> `error-span-count=0`. The user-visible "error" is a **business decline**,
> not a 5xx/crash. The misleading `otel.status_code=ERROR` on the gateway
> spans is what makes a normal decline look like a silent technical failure.

### Fix

Depending on what you actually want, pick the matching fix:

**A. Make happy-path checkout succeed (most common).** Use a valid
Visa/Mastercard test PAN that is **not** `4000000000000002` or
`5105105105105100`, a future expiry, a 3-4 digit CVV, a low amount, and
confirm the runtime mode is `approve`:

```bash
# Confirm the deployed payment mode (manifest reference)
grep -n "PAYMENT_SIMULATION_MODE\|PAYMENT_PROVIDER\|PAYMENT_GATEWAY_SIMULATION_ENABLED" \
  deploy/k8s/oke/shop/deployment.yaml
# expect: PAYMENT_SIMULATION_MODE=approve, PAYMENT_PROVIDER=simulated,
#         PAYMENT_GATEWAY_SIMULATION_ENABLED=true
```

**B. Stop the misleading observability (the real product fix).** A business
`declined` / `review` outcome should **not** set `otel.status_code=ERROR` —
reserve `ERROR` for true faults (Java unreachable, DB write failure,
exceptions). The two emit points are
`shop/server/modules/payments/gateway_emulator.py` (the `_emit_step` helper,
~line 580) and `shop/server/modules/payment_gateway_simulation.py` (~line
268). Fixing this makes Trace Explorer's error-trace quick-picks meaningful
again and prevents the false RCA this lab walks you out of.

**C. Make the decline visible to operators.** Activate the antifraud custom
attributes (`payment.antifraud_reasons`, `payment.verification.decision`,
`payment.error_code`, `payment.decision_source`, `payment.risk_score`) in
the `octo-emdemo-apm` domain so the decline reason is readable without
opening every span. (This is a change in the LogAnalytics-owned APM domain —
out of scope for a read-only lab, but the right operational follow-up.)

**D. Surface declines clearly in the UI.** The storefront's `submitCheckout`
(`shop/server/templates/shop.html`, ~line 1488/1524) treats a 200-with-decline
as a vague error string. Add an explicit *declined* state with the
`payment.error_code` reason and a "try another card" affordance so a designed
decline is never perceived as a system error.

### Verify recovery in APM

Re-run a checkout with a **valid** (non-decline) test card, then return to
**APM → Trace Explorer** and open the new trace:

```text
show spans OperationName, StatusCode where OperationName = 'payment_gateway.credit_card.merchant_authorization_result'
```

**What you see:** the new `merchant_authorization_result` span shows
`payment.status = authorized`, `payment.decision_source` reflects the
approve path, and `otel.status_code` is no longer `ERROR`. The storefront
renders a clean order confirmation with no "payment required" string. You
proved the outcome in the **same surface** where you first saw the symptom.

---

## What to monitor day-to-day (the takeaway checklist)

Keep these panes pinned; this is the order to pivot in for any payment
complaint:

- [ ] **APM — `merchant_authorization_result` decline rate.** Filter on
      `OperationName = 'payment_gateway.credit_card.merchant_authorization_result'`
      and chart the share with `payment.status = declined`. This is your
      *real* payment-failure signal — not the trace fault rate, which stays
      zero for declines.
- [ ] **APM — `payment.decision_source` split.** A spike in
      `java-antifraud-verification-app` declines vs. local declines tells you
      whether the antifraud tier or the local baseline is driving rejections.
- [ ] **Log Analytics — trace-joined decline reasons.** Always carry the
      `trace_id` / `oracleApmTraceId` into the logs; the
      `checkout-payment-correlation` and `payment-gateway-security-triage`
      saved searches turn "a payment failed" into "this card declined for
      this reason".
- [ ] **Watch the trap, not just the colour.** Never conclude "silent
      failure" from `otel.status_code=ERROR` alone — confirm `is-fault` and
      `error-span-count` first. A decline is a *decision*, not a *fault*.

The single most valuable habit: **for any payment symptom, read
`payment.status` + `payment.decision_source` + the trace-level `is-fault`
before you call it a bug.**

## Cleanup

This lab is read-only against the live environment — there is nothing to
tear down. The seeded decline scenario is part of the demo's normal traffic
and self-sustains. If you reproduced a decline in Step 0, the resulting
order simply remains `payment_pending`; no data needs to be removed.

```bash
# Confirm the payment mode is still 'approve' (no global decline left enabled)
curl -sS "https://drones.<DNS_DOMAIN>/ready" \
  | jq '.payment_gateway_simulation_enabled'
# expect: true  (gateway simulation on; mode 'approve' per the manifest)
```

## Verify

```bash
./tools/workshop/verify-18.sh
```

Expected:

```text
✓ found at least one shop.checkout trace in the APM domain (last 7d)
✓ found a payment_gateway.*.merchant_authorization_result span with payment.status = declined
✓ that declined trace is is-fault=false / error-span-count=0 (not a server fault)
✓ upstream HTTP POST /api/java-apm/payment/verify returned http.response.status_code = 200
PASS — Lab 18 complete
```

!!! note "verify-18.sh status"
    Like `verify-17.sh`, this verifier is a **TODO**: it is referenced here
    to keep the lab self-consistent with the verifier convention, but the
    script does not yet ship in `tools/workshop/`. Until it lands, run the
    Step 1-5 APM queries by hand to confirm each ✓ line above. Contributions
    welcome.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No declined traces in Trace Explorer | Window too short (declines are sparse) | Widen the time range to **Last 7 days**; re-run the Step 2 filter |
| Declined trace not under "Errored Traces" | The trace is `is-fault=false` / `error-span-count=0` by design | Don't use the Errored-Traces quick-pick; filter by `OperationName = 'payment_gateway.credit_card.merchant_authorization_result'` and `payment.status = declined` |
| Span attributes panel has no `payment.decision_source` / `payment.risk_score` | Custom antifraud attributes not activated in the APM domain | Read `payment.status` on the `merchant_authorization_result` span; activate the custom attributes (Fix C) to see the full reason |
| Log Analytics returns nothing for the `trace_id` | Field name or source mismatch | Try `trace_id` instead of `oracleApmTraceId`; check both `OCI Unified Schema Logs` (Connector Hub) and `SOC Application Logs` (direct/OKE) sources |
| Every checkout declines, not ~28% | `PAYMENT_SIMULATION_MODE` set to `decline`/`timeout` (highest blast radius) | Confirm the live Deployment/Secret reads `PAYMENT_SIMULATION_MODE=approve` (manifest: `deploy/k8s/oke/shop/deployment.yaml`); env can change without redeploy |
| Java verify/authorize spans missing | Sidecar unreachable — checkout degrades to the local decision, not a 5xx | Confirm `octo-java-app-server-oke` is reachable; `JavaAppServerClient` returns `unreachable` on timeout and keeps the local decision silently |

## Read more

- [Lab 10 — End-to-end debug a failed checkout](lab-10-failed-checkout.md) — the CRM-sync-timeout sibling; RUM-session-first entry point
- [Lab 17 — Root-cause a slow/faulty SQL end-to-end](lab-17-root-cause-apm-logan.md) — the DB-pivot sibling; same `trace_id`-as-join-key discipline
- [Lab 03 — Find a slow SQL from an APM span](lab-03-slow-sql-drill-down.md) — span drill-down + `sql_id` pivot
- [Lab 02 — Trace ↔ Log correlation](lab-02-trace-log-correlation.md) — the `oracleApmTraceId` bridge
- [Architecture → Correlation Contract](../architecture/correlation-contract.md) — the trace↔log join key

---

[← Lab 17](lab-17-root-cause-apm-logan.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Workshop Home](index.md)
