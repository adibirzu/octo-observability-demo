-- AI Studio GenAI errors: LLM failures, guardrail blocks, and tool errors.
-- Source: octo-genai-studio error/guardrail events in Log Analytics.
'Log Source' = 'octo-genai-studio'
| where Severity in ('ERROR', 'WARNING') or 'studio.guardrail.allowed' = 'false'
| stats count as events
   by 'gen_ai.agent.name', 'studio.guardrail.reason', Severity
| sort -events
-- (visualization inferred: table)
