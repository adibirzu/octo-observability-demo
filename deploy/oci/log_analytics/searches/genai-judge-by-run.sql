-- GenAI per-run LLM-as-judge scores (G1): score by run/model/agent, not just an average.
-- Activates once judge scores are stamped on the run as `gen_ai.evaluation.score`
-- (+ `gen_ai.evaluation.name`) — either by an in-process evaluator or the Langfuse
-- score write-back CronJob (see langfuse_apm_sync). Until then this returns empty
-- (the averaged metric genai_judge_score_avg still feeds the Monitoring dashboard).
-- Source: octo-genai-studio spans in Log Analytics.
'Log Source' = 'octo-genai-studio'
| where 'gen_ai.evaluation.score' != null
| stats avg('gen_ai.evaluation.score') as avg_score,
        min('gen_ai.evaluation.score') as min_score,
        count as evaluations
   by 'studio.run_id', 'gen_ai.evaluation.name', 'gen_ai.request.model', 'gen_ai.agent.name'
| sort avg_score
-- (visualization inferred: table)
