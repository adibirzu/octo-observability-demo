-- GenAI estimated USD cost grouped by OCI Generative AI model (AI Studio).
-- Feeds the FinOps tile of the GenAI command center.
-- Source: octo-genai-studio gen_ai.* attributes in Log Analytics.
'Log Source' = 'octo-genai-studio'
| where 'gen_ai.request.model' != null
| stats sum('gen_ai.usage.cost_usd') as cost_usd,
        sum('gen_ai.usage.total_tokens') as total_tokens,
        count as generations
   by 'gen_ai.request.model'
| sort -cost_usd
-- (visualization inferred: bar)
