---
title: "Lab 14 — LLM-as-a-Judge Scoring"
description: "Score AI Studio briefs with Langfuse evaluators and surface scores in OCI Monitoring."
---

# Lab 14 — LLM-as-a-Judge Scoring

!!! info "Lab Facts"
    - **Time:** 25 minutes
    - **Surface:** Langfuse evaluators, OCI Generative AI, OCI Monitoring
    - **Prereqs:** Lab 13 complete; observability-stack deployed; OCI GenAI judge model available

## Objective

Stand up automated quality scoring for AI Studio briefs: create the Langfuse
evaluator templates, judge them with an OCI Generative AI model, and watch the
scores flow into OCI Monitoring (and thus the APM/Grafana views).

## Steps

### 1. Preflight the judge model

```bash
# from services/genai-studio
python scripts/check_oci_genai_structured_output.py \
  --region "${OCI_REGION}" --model "${STUDIO_JUDGE_MODEL:-meta.llama-3.3-70b-instruct}" \
  --api-key-file "${OCI_GENAI_OPENAI_KEY_FILE}"
```

Expect `[PASS] … structured output OK`. Structured output is required for judging.

### 2. Create the evaluator templates

```bash
python scripts/ensure_evaluator_templates.py --env-file .env
# creates: ai-studio-brief-groundedness, ai-studio-sales-accuracy,
#          ai-studio-copy-quality, ai-studio-safety
```

### 3. Generate runs and let evaluators score them

Run a few briefs in AI Studio (Lab 12). In Langfuse, attach the evaluators to the
AI Studio traces (project → Evaluators) so each new run is scored 0..1 with
reasoning.

### 4. Surface scores in OCI Monitoring

```bash
python -m app.sync.langfuse_apm_sync --once --hours 1
# publishes genai_judge_score_avg + genai_judge_scores to namespace octo_genai
```

### What you should see

- Four evaluators listed in Langfuse, each producing a 0..1 score + reasoning.
- `genai_judge_score_avg` on the **OCTO GenAI** OCI Monitoring dashboard.

## Verify

```bash
python scripts/ensure_evaluator_templates.py --list   # 4 evaluator names
echo "Langfuse traces carry score values; OCI Monitoring shows genai_judge_score_avg"
```

## Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| Preflight FAIL | Model lacks structured output | Pick a structured-output model (e.g. Llama 3.3 70B) |
| No scores in Langfuse | Evaluator not attached / default eval model unset | Attach evaluators; set the project default eval model |
| No score metric | Sync not run | Run `langfuse_apm_sync --once` |

## Read More

- [GenAI monitoring (APM + Langfuse)](../observability-v2/ai-studio-genai-monitoring.md)
- [AI Studio](../drone-shop/ai-studio.md)
