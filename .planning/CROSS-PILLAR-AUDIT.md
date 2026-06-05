# Cross-Pillar Wiring Audit (WS7)

Multi-agent audit (cross-pillar-audit.js): 7 pillars, 32 agents, 24 candidate gaps,
**11 confirmed** after adversarial verification. 2026-06-04.

**Verdict:** APM core is fully wired (services emit real service.name/.namespace;
traces+logs reach APM+LA; saved queries match emitted attrs). Breaks sit in
*peripheral* planes — mostly integration/naming mismatches + doc drift, not missing
telemetry. Fixes are surgical repoints + honest disclosures.

## Confirmed gaps & remediation

| # | Pillar | Sev | Gap | Fix | Status |
|---|--------|-----|-----|-----|--------|
| 1 | gateways | HIGH | `otel-gateway` collector deployed nowhere; apps export direct to APM; redaction plane never in path | wire as flag-gated opt-in (`DEPLOY_OTEL_GATEWAY`) + align docs | ✅ resolved (opt-in; off by default — operator repoints exporters to activate) |
| 2 | la-correlation | HIGH | 3 saved searches target source `octo-shop-app-json` not provisioned by default | repoint to `OCI Unified Schema Logs`/`SOC Application Logs` | ✅ fixed |
| 3 | la-correlation | HIGH | searches join on `route`/`http_status`/`Duration` no service emits | use `url_path`/`http_status_code`/`http_response_time_ms` | ✅ fixed |
| 4 | security | HIGH | `checkout-security-checks.sql` queries fields no parser maps (orphaned) | add fieldMaps to `octo-shop-v2.json`/`octo-crm-v2.json` | ✅ fixed |
| 5 | security | MED | WAF dark by default in portable TF stack (no `oci_logging_log` for WAF) | lab-06 prereq disclosed + WAF module gains `enable_waf_logging`/`web_app_firewall_id` → `waf_log_id` | ✅ resolved (`terraform validate` ok; operator supplies external firewall OCID + wires `la_pipeline_waf_*`) |
| 6 | workshop | HIGH | lab-11 cites `verify-11.sh` w/ fabricated PASS, script absent, no disclosure | add lab-18-style TODO disclosure | ✅ fixed |
| 7 | workshop | HIGH | `certify.sh` caps at 10 labs while index sells 18 | scope as core-10 passport + reword index | ✅ fixed |
| 8 | workshop | MED | `verify-17/18.sh` absent; lab-17 has no Verify section | add self-disclosing TODO note in lab-17 | ✅ fixed |
| 9 | workshop | LOW | index:82 format table overstates verifier coverage | soften wording | ✅ fixed |
| 10 | app-telemetry | MED | genai-studio `service.namespace`=`octo-drone-shop` vs fleet `octo` | align source + live-apply to cluster | ✅ fixed in source **and live-applied** to octo-apm-demo-oke (rollout verified `SERVICE_NAMESPACE=octo`) |
| 11 | app-telemetry | LOW | genai-studio lacks `HTTPXClientInstrumentor` | add if/when it calls app peers over HTTP | deferred (no traced HTTP peer today) |
| 12 | correlation-backbone | LOW | contract doc marks emitting services "(planned)" | drop stale markers | ✅ fixed |

## Decisions requiring the operator (live-deploy / topology)

- **otel-gateway** (#1): deploy the central sampling/redaction collector (rewires the
  trace path — needs live validation) **or** delete it as intended-direct topology.
  Docs corrected to match current reality either way.
- **genai-studio service.namespace** (#10): its k8s deploy explicitly sets
  `octo-drone-shop`. Changing the *deployed* value re-groups existing APM topology —
  left to the operator; code default now matches the fleet (`octo`).
- **WAF logging** (#5): porting `oci_logging_log.waf` into the portable `deploy/terraform`
  stack changes apply behavior — staged as a follow-up; lab-06 + README now disclose the
  prerequisite.
