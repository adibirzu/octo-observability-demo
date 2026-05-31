-- GenAI session / thread rollup (G3): multi-turn conversation grouping.
-- Every studio span carries `session.id` (stamped by ContextEnrichmentSpanProcessor),
-- so a session groups all runs of one conversation. Gives OCI APM the session view
-- Langfuse has natively. Source: octo-genai-studio spans in Log Analytics.
'Log Source' = 'octo-genai-studio'
| where 'session.id' != null
| stats count as spans,
        distinctcount('studio.run_id') as runs,
        sum('gen_ai.usage.total_tokens') as total_tokens,
        sum('gen_ai.usage.cost_usd') as cost_usd,
        distinctcount('gen_ai.agent.name') as agents,
        earliest(Time) as first_seen,
        latest(Time) as last_seen
   by 'session.id', 'user.id'
| sort -last_seen
-- (visualization inferred: table)
