# Enterprise CRM Portal

A deliberately vulnerable CRM/ERP application designed for security testing and full-stack observability demonstrations. Part of the OCI-DEMO project.

## Architecture

```
                                    +------------------+
                                    |  OCI Load        |
    Users ──────────────────────────│  Balancer        │
                                    +--------+---------+
                                             |
                                    +--------v---------+
                                    |  FastAPI App      |
                                    |  (Port 8080)      |
                                    |                   |
                                    |  - 10+ CRM pages  |
                                    |  - REST APIs      |
                                    |  - OTel spans     |
                                    |  - RUM injection  |
                                    +--------+---------+
                                             |
                                    +--------v---------+
                                    |  ATP / DB Backend |
                                    |  (OCI-DEMO)       |
                                    +-------------------+

    Telemetry outputs:
    ├── OCI APM (OTel OTLP) ──── Traces (8+ spans/request)
    ├── OCI APM RUM ──────────── Browser performance
    ├── OCI Logging SDK ──────── Structured logs
    ├── Splunk HEC ───────────── Security events
    └── stdout (JSON) ────────── Container logs
```

## Pages (10+)

| # | Page | Route | Module | OWASP Vulnerabilities |
|---|------|-------|--------|----------------------|
| 1 | Dashboard | `/` | dashboard | N+1 queries, slow query simulation |
| 2 | Customers | `/customers` | customers | SQLi, Stored XSS, IDOR |
| 3 | Orders | `/orders` | orders | Price manipulation, IDOR, business logic bypass |
| 4 | Products | `/products` | products | SQLi, verbose errors, no validation |
| 5 | Invoices | `/invoices` | invoices | CSRF, SSTI, sensitive data exposure |
| 6 | Support Tickets | `/tickets` | tickets | Reflected XSS, log injection, open redirect |
| 7 | Reports | `/reports` | reports | Arbitrary SQL, command injection, insecure deserialization |
| 8 | File Manager | `/files` | files | Path traversal, XXE, SSRF, unrestricted upload |
| 9 | Admin Panel | `/admin` | admin | No auth, privilege escalation, config exposure |
| 10 | Settings | `/settings` | simulation | Chaos engineering controls |
| 11 | Login | `/login` | auth | Brute force, mass assignment, weak hashing, session fixation |
| 12 | API Keys | — | api_keys | Weak key generation, timing attack, key enumeration |

## OWASP Top 10 (2021) Coverage

| OWASP | Category | Implemented In |
|-------|----------|---------------|
| A01 | Broken Access Control | customers, orders, invoices, admin, files |
| A02 | Cryptographic Failures | auth, invoices, api_keys |
| A03 | Injection (SQLi, XSS, XXE) | customers, products, tickets, reports, files |
| A04 | Insecure Design | orders, invoices, files |
| A05 | Security Misconfiguration | products, admin |
| A07 | Identification & Auth Failures | auth, api_keys |
| A08 | Software & Data Integrity | reports (deserialization) |
| A09 | Logging & Monitoring Failures | tickets (log injection) |
| A10 | SSRF | files |

## Trace Depth (8+ Spans)

Each request generates 8+ spans:
1. `middleware.entry` — IP, user-agent, URL
2. `auth.check` — session/token validation
3. `request.validate` — content type/length
4. `{module}.{action}` — route handler (auto-instrumented)
5. `db.query.*` — SQLAlchemy auto-instrumented
6. `ATTACK:{TYPE}` — security span (if attack detected)
7. `response.finalize` — status code, duration
8. `health.readiness` — dependency checks

Dashboard summary generates 10+ spans (6 DB queries + middleware).

## Quick Start

```bash
# Clone
git clone https://github.com/adibirzu/enterprise-crm-portal.git
cd enterprise-crm-portal

# Copy environment
cp .env.example .env

# Run locally with Docker Compose
docker compose up -d

# Access
open http://localhost:8080
```

## Load Testing (k6)

```bash
# Local test
k6 run --env BASE_URL=http://localhost:8080 k6/load_test.js

# Multi-location (k6 Cloud)
k6 cloud k6/load_test.js
```

The k6 test includes 3 scenarios:
- **browse**: Simulates real user journeys (ramp 1→25 VUs)
- **api_load**: Constant 20 req/s API throughput test
- **security_probes**: SQLi, XSS, SSRF, path traversal probes

## Issue Simulation

Toggle infrastructure issues at runtime:

```bash
# Simulate DB latency
curl -X POST http://localhost:8080/api/simulate/db-latency \
  -H 'Content-Type: application/json' -d '{"delay_seconds": 3}'

# Simulate DB disconnect (auto-resets after 10s)
curl -X POST http://localhost:8080/api/simulate/db-disconnect

# Error burst (for log/APM testing)
curl -X POST http://localhost:8080/api/simulate/error-burst \
  -H 'Content-Type: application/json' -d '{"count": 50}'

# N+1 query demo
curl http://localhost:8080/api/dashboard/n-plus-one

# Reset all
curl -X POST http://localhost:8080/api/simulate/reset
```

## OCI Integration

### APM (OpenTelemetry)
Set `OCI_APM_ENDPOINT` and `OCI_APM_PRIVATE_DATAKEY` in `.env`.
Traces are exported via OTLP/HTTP to OCI APM.

### RUM (Real User Monitoring)
Set `OCI_APM_RUM_ENDPOINT` and `OCI_APM_RUM_PUBLIC_DATAKEY`.
RUM JavaScript is injected into all HTML pages.

### Logging SDK
Set `OCI_LOG_ID` and `OCI_LOG_GROUP_ID`.
All security events and app logs are pushed to OCI Logging.

### OCI-DEMO topology
Set `MUSHOP_CLOUDNATIVE_URL`, `OCI_DEMO_CONTROL_PLANE_URL`, `OCI_DEMO_BACKEND_URL`,
`ATP_OCID`, `ATP_CONNECTION_NAME`, `APM_CONSOLE_URL`, `OPSI_CONSOLE_URL`,
`DB_MANAGEMENT_CONSOLE_URL`, and `LOG_ANALYTICS_CONSOLE_URL` to expose cross-product
drilldowns and health checks in the UI.

### Splunk HEC
Set `SPLUNK_HEC_URL` and `SPLUNK_HEC_TOKEN`.
Security events are forwarded to Splunk in fire-and-forget mode.

## Kubernetes Deployment

```bash
# Create DB init ConfigMap
kubectl create configmap crm-db-init --from-file=server/db_init.sql

# Deploy
kubectl apply -f deploy/k8s/deployment.yaml

# Deploy against OCI-DEMO / ATP-backed services
kubectl apply -f deploy/k8s/deployment-atp.yaml

# Check status
kubectl get pods -l app=enterprise-crm-portal
kubectl get svc enterprise-crm-portal
```

## Project Structure

```
enterprise-crm-portal/
├── server/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py             # Environment configuration
│   ├── database.py           # SQLAlchemy models + async engine
│   ├── db_init.sql           # PostgreSQL seed data
│   ├── modules/              # CRM modules (12 routers)
│   │   ├── auth.py           # Authentication (A07)
│   │   ├── customers.py      # Customer CRUD (A01, A03)
│   │   ├── orders.py         # Order management (A01, A04)
│   │   ├── products.py       # Product catalog (A03, A05)
│   │   ├── invoices.py       # Invoice management (A02, A04)
│   │   ├── tickets.py        # Support tickets (A03, A09)
│   │   ├── reports.py        # Custom reports (A03, A08)
│   │   ├── admin.py          # Admin panel (A01, A05)
│   │   ├── files.py          # File management (A01, A10)
│   │   ├── dashboard.py      # Analytics + perf demos
│   │   ├── api_keys.py       # API key management (A02)
│   │   └── simulation.py     # Chaos engineering
│   ├── middleware/
│   │   ├── tracing.py        # OTel custom span middleware
│   │   └── chaos.py          # Chaos injection middleware
│   ├── observability/
│   │   ├── otel_setup.py     # OCI APM OTel init
│   │   ├── security_spans.py # MITRE ATT&CK + OWASP spans
│   │   └── logging_sdk.py    # OCI Logging + Splunk HEC
│   ├── templates/            # Jinja2 HTML (with RUM)
│   └── static/               # CSS + JS
├── deploy/
│   └── k8s/                  # Kubernetes manifests
├── k6/
│   └── load_test.js          # k6 multi-scenario load test
├── docker-compose.yml        # App + PostgreSQL
├── Dockerfile
└── requirements.txt
```
