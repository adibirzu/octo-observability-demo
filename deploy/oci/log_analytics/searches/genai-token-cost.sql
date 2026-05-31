-- GenAI token & cost by AI Studio run / model / agent.
-- Source: octo-genai-studio app logs + APM gen_ai.* span attributes shipped to
-- Log Analytics. Referenced by the APM saved query ai_studio_token_cost as a
-- log-analytics pivot keyed on studio.run_id.
--
-- Fields surfaced: Run ID, Model, Agent, input/output/total tokens, estimated
-- USD cost. No colon-parameter placeholders (dashboard-safe).
'Log Source' = 'octo-genai-studio'
| where 'gen_ai.request.model' != null
| stats sum('gen_ai.usage.input_tokens') as input_tokens,
        sum('gen_ai.usage.output_tokens') as output_tokens,
        sum('gen_ai.usage.total_tokens') as total_tokens,
        sum('gen_ai.usage.cost_usd') as cost_usd,
        count as generations
   by 'studio.run_id', 'gen_ai.request.model', 'gen_ai.agent.name'
| sort -cost_usd
