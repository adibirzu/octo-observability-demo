-- AI Studio agent fan-out: invocation count + latency per agent.
-- Shows the supervisor + 5 agents (sales_analyst, evidence, code_interpreter,
-- product_copy, presenter) for one merchandising-brief workflow.
-- Source: octo-genai-studio agent.invoke.* / coordinator.* spans in LA.
'Log Source' = 'octo-genai-studio'
| where 'gen_ai.agent.name' != null
| stats count as invocations,
        avg('Content Size Out') as avg_latency_ms
   by 'gen_ai.agent.name'
| sort -invocations
-- (visualization inferred: bar)
