---
title: "Lab 17 — Root-cause a slow/faulty SQL across APM → Log Analytics → OPS Insights → Database Management"
description: "Inject a faulty SQL fault, then walk the full root-cause path end-to-end: spot it in OCI APM Trace Explorer, pivot by trace_id into Log Analytics, confirm DB-level impact in OPS Insights, drill into the offending statement in Database Management, fix it, and verify recovery in APM."
---

# Lab 17 — Root-cause a slow/faulty SQL end-to-end

## Objective

Learn **what to monitor** and **how to find a root cause** when a backend
service starts erroring on the database. You will inject a known fault,
then drive the same path a real operator follows: **OCI APM → OCI Log
Analytics → OPS Insights → Database Management → fix → verify**. The skill
this lab builds is the *pivot* — carrying one `trace_id` from a slow/failing
span all the way down to the exact SQL statement on the managed database,
then back up to APM to prove recovery.

!!! info "Lab Facts"
    - **Time:** 35 minutes
    - **Surfaces (the 4 you'll pivot across):** OCI APM Trace Explorer · OCI Log Analytics · OPS Insights · Database Management
    - **Service under test:** `octo-workflow-gateway` (Go) → shared Autonomous DB `OCTOATP` (Oracle Database 19c)
    - **Prereqs:** admin sign-in via SSO (a single CRM login mints `octo_session`, so `https://admin.<DNS_DOMAIN>` opens with no second login); OPSI + Database Management enabled on `OCTOATP` (Labs 03 and 08 cover enablement)

## What good looks like

By the end you can state, in one sentence, **which statement on which
database caused the symptom, and the evidence at each layer**:

- **APM** shows a failing/slow span on `octo-workflow-gateway` with a
  `db.statement.preview` and a `trace_id`.
- **Log Analytics**, filtered by that same `trace_id`, shows the
  correlated error log line with the SQL/error detail.
- **OPS Insights** shows the matching blip on `OCTOATP` (SQL / CPU trend).
- **Database Management** shows the offending statement in *Top SQL* with
  its execution detail.
- After disabling the toggle, **APM** shows the span go green again.

That chain — symptom → trace → log → DB metric → SQL → fix → verify — is
the entire lab.

## The fault you'll inject

`octo-workflow-gateway` runs a scheduled sweep against `OCTOATP`. With the
fault lever on, every sweep also fires a **deliberately broken probe**
(`broken_orders_probe`) that runs an invalid statement:

```sql
SELECT non_existing_column FROM orders FETCH FIRST 5 ROWS ONLY
```

This produces a failing span and an Oracle error (`ORA-00904: invalid
identifier`) on a fixed cadence — perfect for a clean root-cause walk.
(If you'd rather drive a *slow* query than a *faulty* one, use the CRM
Chaos preset in the alternative below; the pivot path is identical.)

---

## Step 0 — Inject the error

Pick **one** lever.

### Lever A (primary) — workflow gateway faulty SQL

Set `WORKFLOW_FAULTY_QUERY_ENABLED=true` on the gateway and let one sweep
run. On OKE:

```bash
kubectl set env deployment/octo-workflow-gateway \
  WORKFLOW_FAULTY_QUERY_ENABLED=true -n octo-drone-shop
kubectl rollout status deployment/octo-workflow-gateway -n octo-drone-shop
```

The scheduler sweeps on its poll interval; within one cycle the broken
probe fires. Confirm the lever is live:

```bash
curl -s "https://admin.<DNS_DOMAIN>/api/workflow/overview" \
  | jq '.gateway.faulty_query_enabled'
# expect: true
```

### Lever B (alternative) — CRM Chaos slow-query / error preset

If the gateway isn't reachable, drive the same symptom from the CRM Chaos
admin (`role: chaos-operator`):

```bash
RUN_ID=$(uuidgen)
curl -sS -X POST "https://admin.<DNS_DOMAIN>/api/admin/chaos/apply" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Service-Key: $INTERNAL_SERVICE_KEY" \
  -H "X-Run-Id: $RUN_ID" \
  -d '{"profile":"db-latency","duration_seconds":600,"intensity":"moderate"}' | jq
echo "RUN_ID=$RUN_ID"
```

Or use the UI: **`https://admin.<DNS_DOMAIN>/admin/chaos`** → apply the
**slow-query / error** preset. Note the `run_id` it emits — every signal
carries it (see the [correlation contract](../architecture/correlation-contract.md)).

---

## Step 1 — APM Trace Explorer: spot the failing/slow service

```text
OCI Console → Observability & Management → Application Performance Monitoring → Trace Explorer
```

Scope to the last 15 minutes. The fastest "what's broken right now" filter:

```text
ServiceName = 'octo-workflow-gateway' and StatusCode = 'ERROR'
```

(For Lever B, filter on the slow side instead:
`ServiceName = 'enterprise-crm-portal' and Duration > 500ms`, or pivot by
`attributes."chaos.run_id" = '<RUN_ID>'`.)

**What you see:** a cluster of error traces appearing on the cadence of the
sweep. Sort by most recent and open one.

### Drill to the offending span

In the flame chart, the failing span is `workflow.query.broken_orders_probe`.
Click it. In the right-hand attribute panel, read:

- `workflow.status` = `error`
- `workflow.component` = `oracle-atp`
- `db.statement.preview` = `SELECT non_existing_column FROM orders …`
- `StatusCode` = `ERROR` (Lever B: instead look at the wide `db.*` span and
  its `Duration`)

**Copy the `trace_id`** (32 hex chars) from the trace header. This is your
join key for every layer below.

!!! tip "What to look at first, every time"
    On any failing trace: (1) which **service** owns the failing span,
    (2) the **span name** and its `db.*` / `http.status_code` attributes,
    (3) the **`trace_id`**. Those three answers tell you *where*, *what*,
    and *how to follow it down*.

---

## Step 2 — Log Analytics: pivot by trace_id to the correlated error

Now carry that `trace_id` into the logs. Every app log record is stamped
with the active trace id as `oracleApmTraceId` (the
[correlation contract](../architecture/correlation-contract.md) guarantees
the trace↔log join).

```text
OCI Console → Observability & Management → Logging Analytics → Log Explorer
```

Query (replace `<TRACE_ID>` with the value you copied):

```text
'Log Source' = 'octo-workflow-gateway-json'
  and oracleApmTraceId = '<TRACE_ID>'
  | sort -Time
```

**What you see:** the correlated `ERROR` / `WARNING` line for that exact
run, with the full Oracle error text the truncated span preview only hinted
at:

- `error.message` = `ORA-00904: "NON_EXISTING_COLUMN": invalid identifier`
- `workflow.query_name` = `broken_orders_probe`
- the same `oracleApmTraceId` echoing your `trace_id`

You now know it's a **SQL identifier error against `OCTOATP`**, not a
network, auth, or app-logic failure. (Lever B: the log line shows uniformly
elevated `Duration` carrying your `run_id` instead of an `ORA-` error.)

??? note "No trace_id field in your logs?"
    Some sources name it `trace_id` rather than `oracleApmTraceId`; try
    `... and trace_id = '<TRACE_ID>'`. Both refer to the same W3C trace id.

---

## Step 3 — OPS Insights: confirm the DB-level impact on OCTOATP

A single failing statement is cheap, but the discipline is to confirm the
**database actually felt it** before you touch anything.

```text
OCI Console → Observability & Management → OPS Insights → Database Insights → OCTOATP
```

Open **SQL Insights** (or **Performance → SQL Warehouse**) for the same
time window. **What you see:**

- A small bump in **executions / parse failures** on `OCTOATP` aligned to
  the sweep cadence (the broken probe parses and fails repeatedly).
- For Lever B (db-latency): a visible **CPU / DB-time** rise and the slow
  SQL climbing the **Top SQL by elapsed time** chart.

OPSI keeps long-term history, so this is also where you answer *"is this new
or has it been creeping for a week?"* Note whether the trend is a fresh
spike (our injected fault) or a slow drift.

---

## Step 4 — Database Management: open the managed DB → Top SQL → SQL detail

Now go to the statement itself.

```text
OCI Console → Observability & Management → Database Management → Managed Databases → OCTOATP
  → Performance Hub  (Top SQL / SQL Details)
```

**What you see:**

- For Lever A, the broken probe surfaces as a **failed/parse-error**
  statement in the SQL activity — the text matches
  `SELECT non_existing_column FROM orders …`. Its **Explain Plan** can't be
  produced (the identifier doesn't exist), which *is* the diagnosis.
- For Lever B, find the slow statement by its `db.oracle.sql_id` (copy it
  from the wide APM span's attributes — see
  [Lab 03](lab-03-slow-sql-drill-down.md)) and read its average elapsed
  time, buffer gets, and **Explain Plan** cost. SQL Tuning Advisor may have
  a recommendation.

This is the bottom of the funnel: APM told you *which service and span*,
Log Analytics told you *the exact error*, OPSI told you *the DB felt it*,
and Database Management shows you *the statement on the database* — same
SQL text end to end. The chain is closed.

---

## Step 5 — Conclude root cause, fix, and verify recovery in APM

### Root cause (write it like this)

> `octo-workflow-gateway`'s scheduled sweep was running a broken probe
> (`broken_orders_probe`) that issued `SELECT non_existing_column FROM
> orders`, raising `ORA-00904` against `OCTOATP` on every poll cycle. The
> fault was introduced by the `WORKFLOW_FAULTY_QUERY_ENABLED` lever, not by
> a schema or data change. Customer-facing impact: none (the probe is
> isolated to the sweep); the symptom was a steady stream of ERROR spans.

### Fix — disable the toggle

```bash
# Lever A
kubectl set env deployment/octo-workflow-gateway \
  WORKFLOW_FAULTY_QUERY_ENABLED=false -n octo-drone-shop
kubectl rollout status deployment/octo-workflow-gateway -n octo-drone-shop
```

```bash
# Lever B — clear the chaos profile
curl -sS -X POST "https://admin.<DNS_DOMAIN>/api/admin/chaos/clear" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Service-Key: $INTERNAL_SERVICE_KEY" \
  -H "X-Run-Id: $RUN_ID" \
  -d '{"chaos_id":"<from step 0>"}' | jq
```

### Verify recovery in APM

Return to **APM → Trace Explorer**, same filter
(`ServiceName = 'octo-workflow-gateway' and StatusCode = 'ERROR'`), last
5 minutes. **What you see:** no new error traces after the rollout
completes — the `workflow.query.broken_orders_probe` span stops appearing,
and the next sweep shows only the healthy queries (`orders_backlog`,
`inventory_watch`, `crm_customer_mix`) returning `workflow.status = ok`.
The error rate on the service overview falls back to baseline.

You closed the loop: you proved the fix in the **same surface** where you
first saw the symptom.

---

## What to monitor day-to-day (the takeaway checklist)

Keep these four panes pinned; they are the order you should always pivot in:

- [ ] **APM — error rate & latency per service.** Alarm on
      `StatusCode = ERROR` rate and `Duration` p95 per `ServiceName`. This
      is your *first* signal and where you find the `trace_id`.
- [ ] **Log Analytics — trace-joined errors.** Always carry the
      `trace_id` / `oracleApmTraceId` from a bad span into the logs; that
      one filter turns "something failed" into "this exact SQL/error
      failed".
- [ ] **OPS Insights — OCTOATP SQL & resource trend.** Confirms blast
      radius and tells you *new spike vs. slow creep* before you tune
      anything.
- [ ] **Database Management — Top SQL on the managed DB.** The statement
      itself: elapsed time, Explain Plan, tuning advice — the bottom of the
      funnel.

The single most valuable habit: **never debug a DB symptom without a
`trace_id`.** It is the thread that stitches all four surfaces together.

## Cleanup

```bash
# Ensure the fault lever is off (idempotent)
kubectl set env deployment/octo-workflow-gateway \
  WORKFLOW_FAULTY_QUERY_ENABLED=false -n octo-drone-shop

# If you used Lever B, confirm no chaos profile is still active
curl -s "https://admin.<DNS_DOMAIN>/api/workflow/overview" \
  | jq '.gateway.faulty_query_enabled'
# expect: false
```

No DB cleanup is needed — the broken probe never wrote data, and the
chaos profile self-expires after its `duration_seconds`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| No ERROR traces appear in APM | Sweep hasn't run yet, or lever didn't apply | Wait one poll cycle; re-check `.gateway.faulty_query_enabled` via `/api/workflow/overview` |
| Span has no `db.statement.preview` | Wrong span selected | Click the `workflow.query.broken_orders_probe` child span, not the parent `workflow.scheduler.sweep` |
| Log Analytics returns nothing for the `trace_id` | Field name or source mismatch | Try `trace_id` instead of `oracleApmTraceId`; confirm `'Log Source'` is `octo-workflow-gateway-json` |
| OPSI / DB Management show no data for OCTOATP | Collection lag or not enabled | Allow ~5 min; enable via **ATP → Tools → Operations Insights / Database Management** (Labs 03, 08) |
| APM still shows errors after the fix | Rollout not complete | `kubectl rollout status deployment/octo-workflow-gateway -n octo-drone-shop`; errors stop on the next sweep |

## Read more

- [Lab 03 — Find a slow SQL from an APM span](lab-03-slow-sql-drill-down.md)
- [Lab 09 — Chaos drill](lab-09-chaos-drill.md)
- [Lab 10 — End-to-end debug a failed checkout](lab-10-failed-checkout.md)
- [Architecture → Correlation Contract](../architecture/correlation-contract.md)
- [Stack Monitoring + ATP](../observability-v2/stack-monitoring.md)

---

[← Lab 16](lab-16-genai-rag-retrieval-lineage.md)
&nbsp;&nbsp;|&nbsp;&nbsp;
[Workshop Home](index.md)
