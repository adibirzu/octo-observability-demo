-- GenAI latency percentiles (G2): span-derived p50/p95, independent of Langfuse.
-- Today the latency tiles come from the Langfuse->Monitoring sync; this computes
-- them directly from the studio spans so OCI APM/LA owns the signal. Uses the span
-- duration field shipped to Log Analytics. Source: octo-genai-studio.
'Log Source' = 'octo-genai-studio'
| where 'gen_ai.operation.name' != null
| stats count as calls,
        avg('Content Size Out') as avg_latency_ms,
        pct('Content Size Out', 50) as p50_latency_ms,
        pct('Content Size Out', 95) as p95_latency_ms
   by 'gen_ai.agent.name', 'gen_ai.operation.name'
| sort -p95_latency_ms
-- (visualization inferred: table)
-- NOTE: 'Content Size Out' is the repo's existing latency-proxy field for the
-- octo-genai-studio Log Source (see genai-agent-fanout). Swap to the true span
-- duration field if/when the Log Source maps SpanDuration.
