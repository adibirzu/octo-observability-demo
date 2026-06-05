# WAF module (detection-first)

Additive Terraform module that creates one `oci_waf_web_app_firewall_policy`
per public frontend with:

* OWASP CRS managed protection (log-only by default)
* login rate limit (10 / min, `CHECK` in detection mode)
* freeform tags `deployment-profile=portable`, `waf-mode=DETECTION|BLOCK`

## Variables

| name | purpose |
| --- | --- |
| `compartment_id` | compartment OCID |
| `display_name` | policy name |
| `domain` | public hostname (informational, used for tagging + logs) |
| `mode` | `DETECTION` (default) or `BLOCK` |
| `log_group_id` | OCI Logging log group OCID that receives WAF events |
| `admin_allow_cidrs` | Reserved for future admin-path rules; currently informational |

## Outputs

* `policy_ocid` — attach to your load balancer / WAAS enablement.
* `mode` — normalised to upper case.
* `waf_log_id` — OCID of the optional WAF SERVICE log (empty unless WAF logging is enabled).

## WAF logging → Log Analytics

The portable stack uses an **external** load balancer, so it cannot create the
WAF enforcement point (firewall) itself — and a WAF SERVICE log must source from
that firewall. To light up WAF detections in Log Analytics (the
`waf-vs-app-errors` and `attack-lab-detections` searches):

1. Attach this module's `policy_ocid` to your LB, creating an
   `oci_waf_web_app_firewall`. Note its OCID.
2. Set on the module: `enable_waf_logging = true` and
   `web_app_firewall_id = "<that firewall OCID>"` (plus `log_group_id`). The
   module creates the WAF SERVICE log and exposes it as `waf_log_id`.
3. Feed `waf_log_id` into the root stack's `la_pipeline_waf_*` connector, e.g.
   `waf_log_id_shop = module.waf_shop.waf_log_id`, so detections route to LA.

> The **compute** stack (`deploy/compute/terraform`) wires the LB + firewall +
> log + connector turnkey via `enable_waf_logging`. Use it if you want WAF
> logging without attaching an external LB.

## Flipping to BLOCK

1. Observe 7 days of DETECTION logs in Log Analytics (`octo-waf.parser`).
2. Confirm false-positive rate `< 0.1%` on the `waf-top-rules-fired`
   saved search.
3. Update `var.waf_mode = "BLOCK"` and `terraform apply`.
4. The Coordinator `waf-tighten-suggest` playbook posts a proposal
   diff before any apply.
