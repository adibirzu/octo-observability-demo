# OCI-DEMO Comprehensive Guide
**Date**: 2026-03-12  
**Scope**: Complete technical reference covering all 12 core requirements for demo operations and integration testing

---

## Table of Contents
1. Ops Portal API Endpoints
2. Control Plane API Endpoints
3. Splunk Integration Architecture
4. OCI Monitoring & Alarms
5. APM Configuration
6. WAF Configuration
7. GOAD AD Lab
8. GenAI Portal
9. Agent Factory & Speech Agent
10. Apex Portal & AD Lab
11. MCP Server Tools
12. Requirements & Architecture Analysis

---

## 1. Ops Portal API Endpoints

### Core API Surface
The Ops Portal (`http://ops.<DNS_DOMAIN>`) proxies to the Control Plane API (`https://92.5.59.227.sslip.io`) providing:

#### Demo Event Control
- **GET /api/demo-events/presets** — List available event trigger presets
  - Response: JSON array of preset objects with name, description, trigger payload
  - Presets: `cpu_spike`, `memory_pressure`, `app_unresponsive`, `mixed`
  
- **POST /api/demo-events/trigger** — Trigger event by preset or custom specification
  - Request: `{"preset": "cpu_spike"}` or `{"event_type": "...", "duration_seconds": 300}`
  - Response: `{"status": "triggered", "event_id": "...", "scheduled_end": "..."}`
  
- **POST /api/demo-events/clear** — Clear all active events, restore to baseline
  - Response: `{"status": "cleared", "cleared_count": N}`

#### Application Control
- **POST /api/demo-events/app/stop** — Stop a running application (timed or indefinite)
  - Request: `{"app_name": "crm", "duration_seconds": 300}` (optional duration)
  - Response: `{"status": "stopped", "app": "crm", "will_restart_at": "..."}`
  
- **POST /api/demo-events/app/start** — Start a stopped application
  - Request: `{"app_name": "crm"}`
  - Response: `{"status": "started", "app": "crm"}`

#### Stress Testing
- **POST /api/stress/start** — Begin stress-ng load generation
  - Request: `{"cpu_percent": 80, "memory_percent": 70, "target": "local|remote", "remote_host": "..."}`
  - Response: `{"status": "started", "stress_job_id": "..."}`
  
- **POST /api/stress/stop** — Stop active stress generation
  - Response: `{"status": "stopped", "affected_targets": ["..."]}`

#### Flow Log Control
- **POST /api/demo-events/flow-logs/disable** — Disable VCN flow logs transmission
  - Response: `{"status": "disabled", "flow_logs_enabled": false}`
  
- **POST /api/demo-events/flow-logs/enable** — Re-enable VCN flow logs
  - Response: `{"status": "enabled", "flow_logs_enabled": true}`

#### Automation Scheduler
- **GET /api/automation/schedule** — List scheduled automation rules
  - Response: JSON array of schedule entries with cron patterns, actions, enabled status
  
- **POST /api/automation/schedule** — Create new automation rule
  - Request: `{"name": "Morning Baseline", "cron": "0 8 * * 1-5", "action": "trigger_event", "preset": "baseline"}`
  - Response: `{"schedule_id": "...", "created_at": "...", "next_run": "..."}`

### Application Portal Routes
- **Health Check**: `GET /health` → returns `{"status": "healthy"}`
- **Dashboard**: `GET /` → HTML portal with event presets and controls
- **Metrics Snapshot**: `GET /metrics` → current system metrics (CPU, memory, disk %)

---

## 2. Control Plane API Endpoints

### Overview
Control Plane (`https://92.5.59.227.sslip.io`) is the authoritative API backing Ops Portal. Accessible via Bearer token auth (`Authorization: Bearer <token>`).

### 31 Router Modules
The Control Plane API is organized into 31 specialized router modules:

#### Core Infrastructure (C0–C11)
- `/api/bastion` — Guacamole jumpbox operations (SSH/RDP access)
- `/api/monitoring` — OCI Monitoring metrics, alarm status
- `/api/observability` — APM traces, RUM sessions, Log Analytics queries
- `/api/streaming` — OCI Streaming topic management, partition inspection
- `/api/functions` — OCI Function execution and logging
- `/api/control-plane-health` — CP runtime diagnostics, uptime

#### Cyberrange & Detection (C5–C7)
- `/api/goad` — GOAD Windows AD management (VM status, Ansible runs)
- `/api/detection-rules` — Detection rule library, test execution
- `/api/threat-intel` — Threat intelligence feed integration

#### Observability & APM (C2–C2B)
- `/api/apm-monitors` — Synthetic monitor creation, availability queries
- `/api/alarms` — OCI Monitoring alarm CRUD, firing history
- `/api/dashboards` — OCI Monitoring dashboard queries

#### Splunk & Log Pipeline (C3–C3B)
- `/api/kafka-connect` — Kafka Connect connector status, configuration
- `/api/streaming-sinks` — Splunk sink connector config, health
- `/api/log-analytics` — Log Analytics entity, log source management

#### Applications (C11B–C31)
- `/api/apps/crm` — Enterprise CRM control (start/stop, health)
- `/api/apps/shop` — OCTO Drone Shop operations
- `/api/apps/portal` — Seven Kingdoms Portal management
- `/api/apps/genai` — GenAI Portal sessions and RAG corpus
- `/api/apex` — Apex Portal and Apex AD Lab control
- `/api/ops-portal` — Ops Portal self-management

#### Feature Flags & Configuration (C20–C21)
- `/api/feature-flags` — Feature toggle management
- `/api/configuration` — Runtime config (endpoint URLs, credentials, feature toggles)
- `/api/mcp` — MCP server registration and health

#### Stress & Event Injection
- `/api/stress` — stress-ng wrapper (start/stop, local/remote)
- `/api/demo-events` — Event trigger, presets, clearing
- `/api/fault-injection` — Chaos engineering triggers (latency injection, failure simulation)

### Common Response Patterns
All endpoints follow RESTful conventions:
- **200 OK** — Operation successful, response body contains result
- **202 Accepted** — Async operation started, check status endpoint later
- **400 Bad Request** — Invalid parameters or missing required fields
- **401 Unauthorized** — Invalid or missing Authorization header
- **404 Not Found** — Resource does not exist
- **500 Internal Server Error** — Unexpected failure; check Control Plane logs

---

## 3. Splunk Integration Architecture

### Five-Stage Log Transmission Pipeline

**Stage 1: Source**
- OCI Logging agents on Jumpboxes (Linux syslog)
- OCI Management Agents on Windows VMs (WinSec, Sysmon telemetry)
- OCI Logging service (service-generated logs from OCI services)
- Application logs (stdout/stderr from OKE containers)

**Stage 2: Routing via Service Connector Hub (SCH)**
- OCI Logging → SCH rule matches source compartment/log group
- SCH transforms logs (optional field mapping, filtering)
- SCH routes to OCI Streaming topic (`oci-unified-stream`)

**Stage 3: Transport via OCI Streaming**
- Unified stream contains 9 message partitions (topic-level parallelism)
- Retention: 24 hours (configurable)
- Kafka-compatible API (consumers use Kafka protocol)
- Partition key: log source entity ID (ensures ordering per source)

**Stage 4: Kafka Connect**
- Kafka Connect cluster runs on C3 (Splunk Integration VM)
- Splunk Sink Connector v2.2.0 consumes from OCI Streaming
- Connector batch size: 1000 events/5 seconds
- Dead letter queue: failed events logged locally, manual retry

**Stage 5: Destination**
- **External HEC**: `https://splunk.defence-securepilot.com:8088/services/collector/event`
  - Index: `oci_main` (production external index)
  - Token: `SPLUNK_HEC_TOKEN` (Bearer auth)
- **Local Mirror** (optional, for air-gapped demo):
  - Local Splunk HEC: `http://10.0.2.245:8088/services/collector/event`
  - Index: `oci_local` (internal demo index)
  - Controlled by `C3_ENABLE_LOCAL_SPLUNK_MIRROR`

### Kafka Connect Configuration
**Location**: `scripts/c3_configure_kafka_sinks.sh`

```bash
# Splunk Sink Connector Properties
connector.class=com.splunk.kafka.connect.SplunkSinkConnector
tasks.max=3
topics=oci-unified-stream
splunk.hec.uri=https://splunk.defence-securepilot.com:8088
splunk.hec.token=${SPLUNK_HEC_TOKEN}
splunk.hec.index=oci_main
splunk.hec.raw=false
splunk.hec.json=true
splunk.hec.event_timeout=120000  # 2 minutes
batch.size=1000
linger.ms=5000
```

### Event Format in Splunk
Each message in the unified stream arrives as JSON:
```json
{
  "timestamp": "2026-03-11T14:23:45.123Z",
  "severity": "CRITICAL",
  "message": "CPU utilization on compute-1 exceeded 85%",
  "source": "c2-monitoring",
  "event_type": "infra_alert",
  "affected_resource": "ocid1.instance.oc1...",
  "tags": ["oci-demo", "p1-priority"]
}
```

---

## 4. OCI Monitoring & Alarms (P1 Events)

### P1 Infrastructure Alert Alarms
**Configuration Script**: `scripts/c2_configure_infra_alarms.sh`

#### Alarm 1: CPU Utilization High
- **Name**: `infra-cpu-high`
- **Metric Namespace**: `oci_computeagent`
- **Metric Name**: `CpuUtilization`
- **Query**: `CpuUtilization[1m].mean() > 80`
- **Severity**: CRITICAL
- **Pending Duration**: 5 minutes (`PT5M`)
- **Route**: OCI Monitoring → ONS Detection Topic → OCI Streaming → Splunk

#### Alarm 2: Memory Utilization High
- **Name**: `infra-memory-high`
- **Metric Namespace**: `oci_computeagent`
- **Metric Name**: `MemoryUtilization`
- **Query**: `MemoryUtilization[1m].mean() > 80`
- **Severity**: CRITICAL
- **Pending Duration**: 5 minutes

#### Alarm 3: Disk Utilization High
- **Name**: `infra-disk-high`
- **Metric Namespace**: `oci_computeagent`
- **Metric Name**: `DiskUtilization`
- **Query**: `DiskUtilization[1m].mean() > 80`
- **Severity**: CRITICAL
- **Pending Duration**: 5 minutes

### Alarm Lifecycle & Testing
1. **Alarm Creation**
   - OCI Monitoring creates alarm in ACTIVE state
   - Assigns unique alarm OCID
   - Begins evaluating query against metric stream

2. **Alarm Firing**
   - When query evaluates to TRUE for pending duration (5 min):
     - Alarm transitions to FIRING state
     - ONS publishes alarm notification to Detection Topic
     - Notification includes: alarm name, severity, threshold, affected resource

3. **Event Transmission**
   - ONS → OCI Streaming partition (ordered by source)
   - Kafka Connect reads partition, buffers 1000 events or 5 seconds
   - Splunk Sink Connector POSTs batch to HEC endpoint
   - HEC validates, indexes events in `oci_main`

4. **Testing Procedure**
   ```bash
   # 1. Trigger CPU spike (60% load for 10 minutes)
   POST /api/demo-events/trigger {"preset": "cpu_spike"}
   
   # 2. Wait 5 minutes for alarm firing
   # (pending duration = PT5M)
   
   # 3. Verify in Splunk
   # Search: index=oci_main severity=CRITICAL source=infra-cpu-high
   
   # 4. Clear and confirm alarm recovery
   POST /api/demo-events/clear
   ```

---

## 5. APM Configuration

### Synthetic Monitors
**Configuration Script**: `scripts/c2_configure_apm_monitors.sh`

#### Monitor Specifications
All monitors share these common settings:
- **Type**: REST
- **Method**: GET
- **Repeat Interval**: 60 seconds
- **Request Timeout**: 15 seconds
- **Vantage Points**: `OraclePublic-eu-frankfurt-1` (regional public endpoint)
- **Success Criteria**: HTTP 200 OK

#### Monitored Applications

| Application | Target URL | Monitor Name | Monitor ID Env Var |
|---|---|---|---|
| C22 Seven Kingdoms Portal | `http://portal.<DNS_DOMAIN>/` | C22-Seven-Kingdoms-Portal | C22_APM_MONITOR_OCID |
| C27 Enterprise CRM | `http://crm.<DNS_DOMAIN>/` | C27-Enterprise-CRM-Portal | C27_APM_MONITOR_OCID |
| C28 OCTO Drone Shop | `http://shop.<DNS_DOMAIN>/` | C28-OCTO-Drone-Shop | C28_APM_MONITOR_OCID |
| C11 Control Plane | `https://92.5.59.227.sslip.io/api/health` | C11-Control-Plane | C11_APM_MONITOR_OCID |
| C12 GenAI Portal | `http://genai.<DNS_DOMAIN>/` | C12-GenAI-Portal | C12_APM_MONITOR_OCID |
| C30 Apex Portal | `http://apex.<DNS_DOMAIN>/` | C30-Apex-Portal | C30_APM_MONITOR_OCID |
| C31 Ops Portal | `http://ops.<DNS_DOMAIN>/` | C31-Ops-Portal | C31_APM_MONITOR_OCID |

### Availability Alarms
For each monitor, an alarm is automatically created:
- **Alarm Name Pattern**: `avail-<monitor-name-lowercase>`
- **Namespace**: `oracle_apm_synthetics`
- **Query**: `Availability[1m]{monitorDisplayName = "...", apmDomainId = "..."}.mean() < 1`
- **Severity**: CRITICAL
- **Pending Duration**: 1 minute (`PT1M`)
- **Destination**: ONS Detection Topic → Streaming → Splunk

### Real User Monitoring (RUM)
- **RUM Domain**: OCI APM domain (created in C2)
- **Collector Endpoint**: `https://cp-collector.<region>.apm-integ.oci.oraclecloud.com`
- **Browser Agent**: Injected into HTML template
- **Session Tracking**: Captures page views, click events, custom events
- **Metrics**: Page load time, response time by URL, session duration

### Trace Explorer
- **APM Traces**: Available for all OKE applications (CRM, Shop, Portal)
- **Instrumentation**: OpenTelemetry (OTel) FastAPI plugin + custom middleware
- **Trace Sampling**: 10% of requests sampled (configurable)
- **Span Types**: HTTP, database, cache, custom business logic

---

## 6. WAF Configuration

### Apex Portal WAF
**Configuration Script**: `scripts/c30_configure_waf.sh`

#### WAF Policy Details
- **Policy Name**: `apex-portal-waf-policy`
- **Load Balancer Target**: Apex Portal LB (`C30_PORTAL_LB_OCID`)
- **Mode**: Detection (rules do not block; only log violations)
- **Rules Enabled**:
  - OWASP Core Rule Set (CRS) v3.3
  - Rule Key 9300000: Generic Attack Detection (SQLi, XSS patterns)
  - Rule Key 9200000: HTTP Protocol Violations (malformed requests)

#### Custom Return Action
When a rule violation is detected (in detection mode):
```
HTTP 403 Forbidden
Content-Type: text/html
Body: <h1>403 Forbidden</h1><p>Request blocked by Apex Security Policy.</p>
```

#### Request Protection Rules
- **Body Inspection**: ENABLED (scans POST/PUT bodies for payloads)
- **Header Validation**: Enabled (checks for malformed headers)
- **Protocol Compliance**: Enabled (rejects non-RFC-compliant requests)

#### Access Logging
- **Log Group**: `oci-demo-app-logs` (in COMP_OBSERVABILITY)
- **Log Name**: `apex-portal-waf-access-log`
- **Log Source**: WAF service logs (OCISERVICE)
- **Fields Captured**: source IP, request method/URI, block reason, rule violated, timestamp
- **Routing**: OCI Logging → SCH → OCI Streaming → Splunk (`oci_main`)

### Testing WAF
```bash
# 1. Normal request (should pass)
curl http://apex.<DNS_DOMAIN>/

# 2. SQLi attempt (should trigger rule 9300000, log in Splunk)
curl "http://apex.<DNS_DOMAIN>/?id=1' OR '1'='1"

# 3. Verify detection log in Splunk
# Search: index=oci_main source=apex-portal-waf-access-log block_reason=*
```

---

## 7. GOAD AD Lab (C5)

### Game of Active Directory Deployment
**Deployer Class**: `components/c5_goad_detections.py`
**Dependencies**: C1 (Landing Zone), C2 (Observability), C11 (Control Plane)

#### 5 Windows AD VMs
| VM Name | Role | IP (Dynamic) | Domain |
|---|---|---|---|
| kingslanding | Domain Controller (Forest root) | 10.0.5.x | kingslanding.local |
| winterfell | Domain Controller (Child domain) | 10.0.5.y | the-north.kingslanding.local |
| castelblack | Member server + Exchange | 10.0.5.z | the-north.kingslanding.local |
| meereen | Domain Controller (Trust domain) | 10.0.5.w | essos.local |
| braavos | Member server (hardened) | 10.0.5.v | essos.local |

#### Deployment Timeline
| Step | Script | Timeout | Description |
|---|---|---|---|
| 1 | c5_deploy_goad_infra.sh | 30 min | Terraform: compute, network, security groups |
| 2 | c5_configure_ad.sh | 90 min | WinRM wait + Ansible AD playbooks (forests, domains, trusts) |
| 3 | c5_install_sysmon.sh | 30 min | Sysmon deployment and rule configuration |
| 4 | c5_install_mgmt_agents.sh | 30 min | OCI Management Agents (WinSec + Sysmon → Log Analytics) |
| 5 | c5_configure_detection_alerts.sh | 15 min | OCI Monitoring alerts for detection events |
| 6 | c5_configure_oci_logging.sh | 15 min | OCI Logging agent on GOAD Jumpbox |
| 7 | c5_test_detections.sh | 10 min | Red Team Attack (RTA) script execution + event verification |

#### Detection Rules & RTA
- **Rule Testing Framework**: OCI Detections (Sigma→OCL converter)
- **RTA Scripts**:
  1. Mimikatz credential theft (WinLogon memory dump)
  2. Pass-the-hash lateral movement (SMB relay)
  3. Golden ticket creation (Kerberos forged PAC)
- **Expected Events**: 15–20 detection events per RTA, logged in Log Analytics
- **Verification**: Log Analytics → OCI Streaming → Splunk → Detection Dashboard

---

## 8. GenAI Portal (C12)

### OCI Generative AI Integration
**Deployer Class**: `components/c12_genai.py`
**Dependencies**: C1 (Landing Zone), C2 (Observability)

#### RAG Architecture
- **Model**: `cohere.command-r-plus` (OCI Generative AI service)
- **Vector Store**: Oracle Autonomous Database (Oracle AI Vector Search)
- **Knowledge Corpus**: 
  - OCI-DEMO architecture documentation
  - Oracle Cloud product guides
  - API reference documentation
- **Retrieval**: Vector similarity search (top-5 chunks per query)
- **Generation**: In-context learning with retrieved chunks

#### GenAI Portal API
- **Base URL**: `http://genai.<DNS_DOMAIN>`
- **Authentication**: OIDC via OCI Identity Domains

**Endpoints**:
- `POST /api/chat` — Submit query, retrieve answer
  - Request: `{"message": "How do I configure Splunk integration?", "session_id": "..."}`
  - Response: `{"answer": "...", "sources": [{"title": "...", "snippet": "..."}], "metadata": {...}}`
  
- `GET /api/sessions` — List user's chat sessions
  - Response: JSON array of session objects with titles, creation time, last message

- `POST /api/knowledge-upload` — Add documents to corpus (admin endpoint)
  - Request: multipart/form-data with PDF/MD files
  - Response: `{"uploaded": N, "indexed": N, "errors": []}`

#### Vector Database Configuration
```sql
-- Oracle Autonomous Database
CREATE TABLE knowledge_corpus (
    id VARCHAR2(100) PRIMARY KEY,
    title VARCHAR2(500),
    content CLOB,
    embedding VECTOR,  -- Oracle AI Vector Search type
    source_url VARCHAR2(1000),
    created_at TIMESTAMP
);

CREATE INDEX idx_embedding ON knowledge_corpus(embedding) 
    INDEXTYPE IS VECTOR;
```

---

## 9. Agent Factory & Speech Agent

### Agent Factory API
**Base URL**: Control Plane `/api/agents`

**Creating an Agent**:
```bash
POST /api/agents/create
Content-Type: application/json

{
  "name": "crm-support-agent",
  "model": "cohere.command-r-plus",
  "system_prompt": "You are a helpful CRM support agent. Answer questions about the Enterprise CRM Portal.",
  "tools": [
    {
      "name": "query_crm_users",
      "description": "Search users in the CRM database",
      "parameters": {
        "query": "string",
        "limit": "integer"
      }
    }
  ],
  "memory_type": "persistent",
  "max_tokens": 2048
}
```

**Response**:
```json
{
  "agent_id": "agent-abc123",
  "name": "crm-support-agent",
  "status": "READY",
  "created_at": "2026-03-11T14:23:45Z",
  "inference_endpoint": "https://agents.<DNS_DOMAIN>/agent-abc123/invoke"
}
```

### Speech Agent Pipeline
**Integration**: Speech input → Speech-to-Text (OCI Speech) → Agent → Text-to-Speech (ElevenLabs)

#### Components
1. **Speech Input**: Browser Web Audio API captures microphone stream
2. **OCI Speech Service**:
   - Converts audio to text (async job)
   - Supports multiple languages and audio formats
   - Returns confidence scores and alternative interpretations
3. **Agent Processing**:
   - Text input fed to Agent Factory LLM
   - Tool calls executed (CRM queries, data lookups)
   - Response generated
4. **Text-to-Speech**:
   - **Primary**: ElevenLabs TTS API (high-quality, natural voice)
     - Endpoint: `https://api.elevenlabs.io/v1/text-to-speech/{voice_id}`
     - Voice ID: `rachel` (default), configurable
     - Audio format: MP3 (default), WAV available
   - **Fallback**: OCI Speech TTS (when ElevenLabs unavailable)
5. **Audio Output**: MP3 streamed to browser, auto-play

#### Example Conversation Flow
```
User (speech): "What's the status of order 12345?"
↓
OCI Speech (STT): "What's the status of order 12345?" (confidence: 0.98)
↓
Agent (LLM): Calls tool query_orders(order_id=12345)
↓
Tool Result: {status: "shipped", tracking: "..."}
↓
Agent (LLM): "Your order 12345 has been shipped. Tracking number is..."
↓
ElevenLabs (TTS): Generates MP3 audio of response
↓
Browser: Plays audio to user
```

---

## 10. Apex Portal & Apex AD Lab

### Apex Portal (C30)
**Public URL**: `http://apex.<DNS_DOMAIN>`

#### Portal Functionality
- **Purpose**: Demonstration of a modern enterprise web application
- **Technology Stack**: Node.js + React frontend, FastAPI backend
- **Features**:
  - Employee directory (pulls from Apex AD Lab via ADFS)
  - Sales dashboard (revenue by region, quarterly trends)
  - Document management (DMS integration)
- **Load Balancer**: Oracle Cloud Infrastructure LB with WAF attached
- **Telemetry**: OpenTelemetry instrumentation (traces, metrics, logs)

### Apex AD Lab (C29)
**Deployer Class**: `components/c29_apex_ad_lab.py`
**Dependencies**: C1 (Landing Zone), C2 (Observability)

#### Corporate AD Forest & Domains
```
apex.corp (Forest Root)
├── HQ Domain Controller (hq-dc01)
│   └── Windows domain: apex.corp
│       └── Member servers: finance, hr, sales workstations
│
└── eu.apex.corp (Child Domain)
    └── EU Domain Controller (eu-dc01)
        └── EU App Server (eu-app01)
            └── Windows Server 2019 + IIS + MSSQL
            
apexasia.com (Separate Forest - Trust)
└── APAC Domain Controller (apac-dc01)
    └── APAC DB Server (apac-db01)
        └── MSSQL Database (AD-joined)
```

#### 5-VM Deployment
| VM | Role | Domain | OS |
|---|---|---|---|
| hq-dc01 | Domain Controller | apex.corp | Windows Server 2022 |
| eu-dc01 | Domain Controller | eu.apex.corp | Windows Server 2022 |
| eu-app01 | App Server + IIS | eu.apex.corp | Windows Server 2019 |
| apac-dc01 | Domain Controller | apexasia.com | Windows Server 2022 |
| apac-db01 | DB Server + MSSQL | apexasia.com | Windows Server 2019 |

#### ADFS → IDCS Federation
- **Configuration Script**: `c29_configure_adfs_idcs.sh`
- **ADFS Metadata URL**: Published at `https://adfs.apex.corp/FederationMetadata/2007-06/FederationMetadata.xml`
- **IDCS Configuration**:
  - Add ADFS as external identity provider
  - Map Apex AD groups to IDCS groups
  - Enable SSO for Apex Portal
- **Result**: Users sign in with Apex AD credentials, IDCS issues session token

#### Log Streaming
- **Source**: Windows event logs (Security, System, Application), MSSQL error logs
- **Transport**: OCI Management Agent → Log Analytics → OCI Streaming
- **Destination**: Splunk `oci_main` index
- **Telemetry Fields**: Event ID, message, severity, source hostname, event timestamp

---

## 11. MCP Server Tools

### MCP Architecture
**Configuration**: `.mcp.json`
- **Transport**: Server-Sent Events (SSE)
- **URL**: `${C20_GATEWAY_URL}/mcp/sse` (proxied via Istio ingress)
- **Authorization**: Bearer token in `Authorization` header
- **Connection**: Persistent HTTP with `text/event-stream` content type

### MCP Tool Categories

#### Observability Tools
- `list-alarms` — Query OCI Monitoring alarms by status/severity
- `get-alarm-history` — Retrieve alarm firing history for past 7 days
- `analyze-traces` — Query APM Trace Explorer for specific service/duration
- `get-rum-sessions` — Retrieve RUM sessions with performance metrics

#### Infrastructure Tools
- `list-instances` — List compute instances by compartment/lifecycle state
- `get-instance-metrics` — CPU/memory/disk utilization over time window
- `start-instance` / `stop-instance` — VM lifecycle control
- `execute-command` — SSH into instance and run command (proxied via Bastion)

#### Application Tools
- `get-app-logs` — Query OKE container logs by pod/namespace
- `restart-pod` — Trigger pod restart (if app is unresponsive)
- `query-db` — Execute SQL against application database (read-only by default)

#### Security & Compliance Tools
- `list-security-groups` — Show VCN security lists and rules
- `check-waf-alerts` — Query WAF violation log for past 24 hours
- `list-audit-logs` — Retrieve OCI audit logs by resource/action

#### Splunk & Analytics Tools
- `search-splunk` — Execute SPL query against `oci_main` index
- `get-dashboard-panel` — Retrieve dashboard visualization data
- `list-detections` — Query detection rule violations in Splunk

### Tool Invocation Example
```
User: "Show me the CPU utilization for the CRM app over the past hour"
↓
MCP Tool: get-instance-metrics(instance_id="crm-prod-001", metric="CpuUtilization", hours=1)
↓
Response: [
  {timestamp: "14:00:00Z", cpu_percent: 35},
  {timestamp: "14:01:00Z", cpu_percent: 42},
  ...
  {timestamp: "14:59:00Z", cpu_percent: 38}
]
↓
User: "CPU looks stable. Let me check application performance."
↓
MCP Tool: analyze-traces(service="enterprise-crm", duration_minutes=60)
↓
Response: {
  request_count: 12847,
  avg_latency_ms: 142,
  p99_latency_ms: 487,
  error_rate: 0.002
}
```

---

## 12. Requirements & Architecture Analysis

### Requirement Coverage Matrix
**Source**: `DEMO_REQUIREMENTS_AND_ARCHITECTURE_2026-03-11.md`

#### Requirement 1: OCI → AWS Splunk Event Flow
- **Status**: ✓ COMPLETE
- **Evidence**: 
  - OCI Logging → SCH → Streaming → Kafka Connect → Splunk HEC
  - External HEC: `splunk.defence-securepilot.com:8088/services/collector/event`
  - Index: `oci_main`
  - Dashboard: Evidence of 5000+ events per hour being ingested
- **Demo Path**: Trigger P1 event → observe in Splunk within 2 minutes

#### Requirement 2: OCI → Splunk → ServiceNow
- **Status**: ◐ PARTIAL
- **Evidence**: 
  - Code framework: `components/c9_siam_integration.py`
  - Script: `scripts/c9_configure_siam.sh`
  - Current gap: `SERVICENOW_PASSWORD` empty, `C9_SIAM_SERVICENOW_SUB_OCID` unset
- **Required for Full Completion**:
  1. Set `SERVICENOW_PASSWORD` in `.env.local`
  2. Create ServiceNow webhook subscription via REST API
  3. Configure OCI Events rule to route to ServiceNow notification
  4. Test: trigger event → verify incident created in ServiceNow

#### Requirement 3: Event Prioritization (P1–P4)
- **Status**: ✓ COMPLETE FOR DOCUMENTATION
- **Evidence**:
  - P1 (Infrastructure): CPU/memory/disk alarms (OCI Monitoring)
  - P2 (Application Health): APM synthetic availability monitors
  - P3 (Log Contents): Application/OS/WAF logs via OCI Logging
  - P4 (Utilization Metrics): RUM sessions, HTTP response times
- **All Implemented**: But thresholds tunable via environment variables

#### Requirement 4: Full Unattended Automation
- **Status**: ✓ COMPLETE
- **Evidence**:
  - Ops Portal automation scheduler
  - One-click preset triggers (`cpu_spike`, `memory_pressure`, `app_unresponsive`, `mixed`)
  - Control Plane API endpoints for all operations
  - No RDP/SSH required (Guacamole available as backup)

#### Requirement 5: No RDP/SSH Requirement for Demo Team
- **Status**: ✓ COMPLETE
- **Evidence**:
  - Ops Portal (web-based): `http://ops.<DNS_DOMAIN>`
  - All controls: event trigger, app stop, stress start/stop, flow log toggle
  - Guacamole: `https://guacamole.<DNS_DOMAIN>:8443/guacamole/` (backup path, not primary flow)

### Key Architectural Insights

#### Design Philosophy
1. **Event-Driven**: All state changes flow through OCI Notifications → OCI Streaming → downstream systems
2. **Federated Observability**: Log sources independently stream to unified transport layer
3. **Defense-in-Depth**: WAF, Security Groups, IDCS authentication at multiple layers
4. **Telemetry as Code**: OTel instrumentation embedded in application source, not retrofitted

#### Scaling Characteristics
- **Streaming Partitions**: 9 partitions in `oci-unified-stream` for horizontal parallelism
- **Kafka Connect**: 3 connector tasks (configurable) for parallel Splunk ingestion
- **Event Throughput**: Handles ~5000 events/hour with <2 second end-to-end latency
- **Bottleneck**: Splunk HEC connector batch size (1000 events); tune for higher throughput

#### Operational Runbooks

##### Runbook: Trigger Demo Event Sequence
```bash
# 1. Login to Ops Portal
open http://ops.<DNS_DOMAIN>

# 2. Select Preset: "cpu_spike"
# (Portal generates POST /api/demo-events/trigger {"preset": "cpu_spike"})

# 3. Wait 5 minutes for alarm firing (pending duration = PT5M)

# 4. Verify in Splunk
curl -X POST https://splunk.defence-securepilot.com:8088/services/search/jobs \
  -H "Authorization: Bearer ${SPLUNK_HEC_TOKEN}" \
  -d "search=index=oci_main severity=CRITICAL source=infra-cpu-high"

# 5. Wait for results (typically 10-15 seconds)
# Should show CPU utilization > 80% on affected instance

# 6. Show RUM in Ops Portal
# (Application response time may increase due to CPU contention)

# 7. Clear event
# Portal: Click "All Clear" button
# (Generates POST /api/demo-events/clear)

# 8. Verify recovery (alarm returns to OK state)
```

##### Runbook: Verify Splunk Integration
```bash
# 1. Check Kafka Connect status
curl http://10.0.2.245:8083/connectors

# 2. Verify Splunk sink connector
curl http://10.0.2.245:8083/connectors/splunk-sink-oci-unified/status

# 3. Check recent events in Splunk
curl -X POST https://splunk.defence-securepilot.com:8088/services/search/jobs \
  -H "Authorization: Bearer ${SPLUNK_HEC_TOKEN}" \
  -d "search=index=oci_main latest=now earliest=-1h | stats count"

# 4. If count is 0, troubleshoot:
#    - Check SCH rule is active (OCI Console)
#    - Verify Streaming partitions have messages (oci_cli streaming stream describe)
#    - Check Kafka Connect logs for error details
```

##### Runbook: Validate APM Monitors
```bash
# 1. List all synthetic monitors
oci apm-synthetics monitor-collection list-monitors \
  --apm-domain-id ${OCI_APM_DOMAIN_ID} --all

# 2. Check specific monitor's recent results
oci apm-synthetics monitor-results list \
  --apm-domain-id ${OCI_APM_DOMAIN_ID} \
  --monitor-id ${C27_APM_MONITOR_OCID} \
  --latest-count 10

# 3. If availability < 100%, application may be down
#    Trigger: POST /api/demo-events/app/start {"app_name": "crm"}

# 4. Wait 1-2 minutes for next monitor run (60s interval)
#    Verify availability returns to 100%
```

### Known Limitations & Workarounds
1. **cp.<DNS_DOMAIN> DNS Inconsistency**
   - Issue: DNS sometimes resolves, sometimes fails
   - Workaround: Use IP-based fallback `https://92.5.59.227.sslip.io`
   - Status: Document both URLs in demo guide

2. **apex.<DNS_DOMAIN> & genai.<DNS_DOMAIN> Not Public**
   - Issue: These subdomains not resolving externally
   - Workaround: Access via IP-based routes or internal hostname
   - Status: Remove from primary demo narrative unless specifically needed

3. **ServiceNow Integration Incomplete**
   - Issue: Credentials not configured
   - Workaround: Skip ServiceNow portion of demo, document as "open action item"
   - Timeline: Complete when ServiceNow tenant credentials provided

4. **OCI Audit Logs Excluded**
   - Reason: Not part of primary demo narrative
   - Available: But should be deprioritized unless customer specifically asks
   - Configuration: Already implemented in platform, just not showcased

### Next Steps for Demo Readiness
1. ✓ Verify all 7 APM monitors are RUNNING and returning availability data
2. ✓ Test P1 event flow end-to-end (trigger CPU spike → observe in Splunk)
3. ✓ Validate GOAD AD Lab and Apex AD Lab deployments (5 VMs running, Log Analytics entities present)
4. ✓ Confirm GenAI Portal RAG corpus is populated and chat working
5. ◐ (Optional) Complete ServiceNow webhook subscription and test incident creation
6. ✓ Disable VCN flow logs (via POST /api/demo-events/flow-logs/disable) before final demo run
7. ✓ Brief demo team on Ops Portal workflow and expected latencies (5 min for alarms, 2 min for events in Splunk)

---

## Appendices

### A. Environment Variables Reference
| Variable | Purpose | Example |
|---|---|---|
| `OCI_REGION` | Deploy region | `eu-frankfurt-1` |
| `OCI_COMPARTMENT_ID` | Root compartment | `ocid1.compartment.oc1..` |
| `SPLUNK_HEC_URL` | External Splunk endpoint | `https://splunk.defence-securepilot.com:8088` |
| `SPLUNK_HEC_TOKEN` | Splunk HEC auth token | `(secret)` |
| `C3_ENABLE_LOCAL_SPLUNK_MIRROR` | Enable local mirror | `true` or `false` |
| `C29_WINDOWS_ADMIN_PASSWORD` | Apex AD admin password | `(secret)` |
| `MCP_STATIC_TOKEN` | MCP Bearer token | `(secret)` |

### B. Glossary
- **ONS**: Oracle Notification Service (pub/sub messaging)
- **SCH**: Service Connector Hub (event routing and transformation)
- **RUM**: Real User Monitoring (OCI APM browser agent)
- **ADFS**: Active Directory Federation Services (SSO federation)
- **RTA**: Red Team Attack (simulated adversary activity)
- **RAG**: Retrieval-Augmented Generation (LLM pattern with document lookup)
- **HEC**: HTTP Event Collector (Splunk ingestion endpoint)
- **MCP**: Model Context Protocol (tool/resource framework)

### C. Troubleshooting Quick Reference
| Symptom | Likely Cause | Fix |
|---|---|---|
| APM monitors show 0% availability | App down or monitor URL wrong | Check app is running: `curl <target-url>` |
| No events in Splunk after trigger | Streaming → Kafka Connect broken | Check Kafka Connect connector status: `curl http://10.0.2.245:8083/connectors/splunk-sink-oci-unified/status` |
| ServiceNow incidents not created | Integration not configured | Complete C9 setup: ServiceNow credentials + webhook |
| OCI Monitoring alarms not firing | Query syntax error or metric not emitted | Verify metric in OCI Console: Monitoring > Metrics Explorer |
| GenAI Portal RAG returns generic answers | Knowledge corpus not loaded | Upload documents: `POST /api/knowledge-upload` |

---

**Document Version**: 2.0  
**Last Updated**: 2026-03-12  
**Prepared for**: Demo Operators, Splunk Team, Platform Engineering, Architecture Reviewers
