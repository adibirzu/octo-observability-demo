# Article screenshots

These images support the end-to-end observability article (kept as a local draft and
published externally). They are **committed** so they render on GitHub and can be reused
in the repo README or the Medium / learnoci.cloud post.

**Redact before you commit — these go public.** Screenshots of the OCI Console can show
OCIDs, public/private IPs, tenancy names, DB unique names, and topology, and an image cannot
be regex-redacted the way text can. Before adding a PNG here: crop or blur every OCID, IP,
tenancy/namespace string, db unique name, and email. If in doubt, leave it out.

## Shots to capture

| File | What to capture | Redact before publishing |
|------|-----------------|--------------------------|
| `01-apm-trace-waterfall.png` | APM Trace Explorer — the checkout trace (shop → Java → ATP), payment span expanded | APM domain OCID in the URL |
| `02-invoice-blob-pdf.png` | CRM invoices page rendering a PDF served from the ATP `invoices.pdf_data` BLOB | customer PII on the invoice |
| `03-apm-java-app-server.png` | APM **App Servers** view for the Java payment service (Apdex, heap, GC) | host names / instance OCIDs |
| `04-loganalytics-trace-drilldown.png` | Log Analytics — `trace-drilldown` results for one `oracleApmTraceId` | log-group OCID, client IPs |
| `05-dbmgmt-sqlid-drilldown.png` | Database Management performance hub for `OCTOATP` with the `sql_id` selected | DB OCID, db unique name |

Keep filenames stable so the article's relative links resolve once the PNGs are dropped in.
