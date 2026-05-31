-- GenAI token throughput over time (AI Studio).
-- Total input/output tokens per interval for the GenAI command center.
-- Source: octo-genai-studio app logs + APM gen_ai.* span attributes in LA.
-- Dashboard-safe: no colon-parameter placeholders.
'Log Source' = 'octo-genai-studio'
| where 'gen_ai.usage.total_tokens' != null
| timestats sum('gen_ai.usage.input_tokens') as input_tokens,
            sum('gen_ai.usage.output_tokens') as output_tokens,
            sum('gen_ai.usage.total_tokens') as total_tokens
-- (visualization inferred: line)
