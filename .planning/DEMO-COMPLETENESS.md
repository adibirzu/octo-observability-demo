# Demo Completeness — Six-Pillar Assessment

Assessed 2026-06-04. The demo is **substantially complete at the source level**;
the gaps are (a) a few quality/coherence issues now fixed, and (b) live-deploy
validation that requires an OCI tenancy (operator-run — emdemo is production/read-only).

## Pillar status

| # | Pillar | Evidence | Source status | To be "fully working" |
|---|--------|----------|---------------|------------------------|
| 1 | **Application telemetry** | shop/crm/genai-studio FastAPI + OTel + APM + RUM (`rum-advanced.js`); Java payment sidecar w/ APM agent | ✅ Complete | Live: `make smoke` confirms `/ready` + APM/RUM/logging configured |
| 2 | **Gateways** | `services/otel-gateway`, workflow gateway (`test_workflow_gateway_proxy`), `apm-java-demo` payment gateway, API GW edge | ✅ Complete | Live: traffic → gateway spans visible in APM |
| 3 | **Error correlation in Log Analytics** | 20+ saved searches: `checkout-payment-correlation`, `trace-to-logs`, `service-health-errors`, `melts-collection-completeness`, `oke-kubernetes-trace-correlation` | ✅ Complete | Live: `tools/la-saved-searches/apply.sh` + Console |
| 4 | **Security log use-cases** | WAF lab-06; `attack-lab-detections.sql`, `rule-api-gateway-threat-count.sql`, `checkout-security-checks.sql`, `api-gateway-edge-detections.sql`; Data Safe + Cloud Guard modules | ✅ Strong | Live: cap-validated; promote to prod after review |
| 5 | **Complete workshop** | 18 labs (lab-01→18) across all pillars; index spine now coherent (was "10 labs") | ✅ Complete | `tools/workshop/verify-NN.sh` per lab against a live deploy |
| 6 | **GenAI monitoring** | genai-studio + Langfuse + LLMetry; 8 `genai-*` LA searches; labs 12–16; `langfuse_apm_sync` CronJob | ✅ Complete | Live: AI Studio enabled + Langfuse reachable |

## Fixed this round (commit 9be3c71)

- **`make test` was RED** (test-docs): mkdocs `--strict` aborted on a broken link
  in lab-13, masking a second failure — the production tenancy name inlined in 4
  published docs. Both fixed; gate now EXIT 0.
- **Workshop index** corrected 10→18 labs + six-pillar framing + objectives 10–12.

## Remaining gaps (concrete)

| Gap | Type | Owner |
|-----|------|-------|
| 35 shop/crm/services pytest **collection errors** (duplicate test basenames; swallowed by `\|\| true`) | Source quality — real test signal is hidden | fixable here |
| No single **capstone lab** weaving all 6 pillars in one narrative (10 & 18 are focused RCA) | Workshop polish | optional |
| **Live end-to-end validation** (deploy → traffic → trace/log/metric/security/GenAI all visible) | Runtime — needs OCI deploy | operator (`make bootstrap` → `make verify` → `make smoke`) |
| Cross-pillar **wiring audit** (every instrumented service → gateway → LA field → saved search → lab) | Deep source audit | best as a multi-agent workflow |

## What I cannot do from here

- **Deploy / live-verify**: emdemo is production (read-only outside LogAnalytics);
  ARM laptop can't build amd64 images locally. The operator runs the deploy +
  `make smoke`/`make verify` against a tenancy.
