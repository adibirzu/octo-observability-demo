---
title: "Lab 19 — Six-pillar workshop capstone"
description: "Investigate a synthetic declined payment across six observability pillars."
---

# Lab 19 — Six-pillar workshop capstone

**Time:** 40 minutes. **Prerequisite:** the story in [Lab 18](lab-18-payment-failure-rca-apm.md). This exercise works offline: use only the synthetic records below. No account, service, or network access is required.

## Objective and presenter setup

A customer reports that payment failed. Lead the group from the order to the gateway, then across all six pillars. Ask attendees to record each join key, observation, and unresolved question before revealing the answer. The records are invented for this exercise; they are not provider-verified telemetry.

## Evidence packet

All records describe the same fictional five-minute window. Values are illustrative, not measured production data.

| Pillar | Synthetic evidence | Handoff |
|---|---|---|
| Application telemetry | Order `order-1042`: checkout HTTP 200, `payment_required=true`; trace `0123456789abcdef0123456789abcdef` has `is-fault=false`, `error-span-count=0`. Gateway span `payment_gateway.credit_card.merchant_authorization_result` has `payment.status=declined`, risk score 99, and `otel.status_code=ERROR`. Antifraud verify returned HTTP 200. | Order → trace ID → gateway span. A red span alone does not establish a server fault. |
| Metrics, alarms and gateways | Gateway metric for the window: 1 decline out of 4 decisions; alarm threshold: more than 50% declines. Alarm state: not firing. | Gateway decision → same window and service. The aggregate is context, not proof about this order. |
| Log Analytics correlation | Log: `oracleApmTraceId=0123456789abcdef0123456789abcdef order_id=order-1042 message="Simulated payment gateway decision" reason=high_risk`. | Trace ID → log field; order ID corroborates the join. |
| Infrastructure and database health | Synthetic service health: ready; database operation for `order-1042`: saved, 12 ms. | Order ID → database record; same window → service health. Neither proves every dependency is healthy. |
| Security log use-cases | Security signal `signal-1042`: antifraud high-risk decision for `order-1042`, score 99. | Order ID → security signal. A risk score is a decision input, not proof of fraud. |
| GenAI monitoring | GenAI observation `observation-1042`: assistant summarized `order-1042` as a declined payment and cited `signal-1042`; evaluation: not run. | Order ID and signal ID → observation. The generated summary is a claim, not independent confirmation. |

## Exercise

1. **Application:** From the order, find the trace and gateway decision. Why can HTTP 200 coexist with a declined payment? Carry the trace ID forward.
2. **Metrics:** Compare the window's decline fraction with the alarm threshold. Does the alarm prove this order succeeded? Carry the gateway and time window forward.
3. **Logs:** Match `oracleApmTraceId` to the trace and check the order ID. What reason does the log supply? Carry the order ID forward.
4. **Infrastructure:** Find the matching order save and service health. What do they show, and what remains unknown? Carry the order ID forward.
5. **Security:** Match the security signal to the order. Does a high risk score prove fraud? Carry the signal ID forward.
6. **GenAI:** Match the observation to the order and signal. Is its summary independently verified? What evaluation evidence is missing?

## Presenter answer and evidence classes

The synthetic order was saved and checkout returned HTTP 200, while the gateway declined payment after an antifraud high-risk decision. The trace-level fields describe no recorded fault despite the gateway span's error attribute. The joined log and security signal support the fictional decision; they do not prove fraud. The metric is window-level context, and the database record only covers the supplied operation. The GenAI observation repeats the decision and its evaluation is **unverified**. All six records are **synthetic fixture evidence**; none is a live observation, provider verification, or proof of recovery.

## Verify and discuss

An attendee completes the lab by naming all six pillars, the trace and order joins, the decline reason, the alarm result (25% is below 50%), and the unevaluated GenAI claim. Ask what additional independent evidence would be needed before changing an antifraud rule or claiming recovery. A live follow-up requires separately authorized access and fresh provider readback; this offline exercise makes no live changes.

[← Lab 18](lab-18-payment-failure-rca-apm.md) | [Workshop Home](index.md)
