#!/usr/bin/env python3
"""Preflight: does an OCI GenAI model support structured output for Langfuse judging?

Langfuse LLM-as-a-judge evaluators require the judge model to return structured
JSON. OCI Generative AI is reached through Langfuse's OpenAI-compatible endpoint:
    https://inference.generativeai.<region>.oci.oraclecloud.com/openai/v1
Not every model honours json_schema / tool calling there. Run this BEFORE setting
a model as the Langfuse default eval model.

This is a thin, dependency-light probe: it calls the OpenAI-compatible chat
endpoint with a tiny json_schema request and reports whether valid JSON came back.

Usage:
    python scripts/check_oci_genai_structured_output.py \
        --region eu-frankfurt-1 --model meta.llama-3.3-70b-instruct \
        --api-key-file ~/.oci/generated-secrets/<oci-genai-key>.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

_PROBE_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "judge_score",
        "schema": {
            "type": "object",
            "properties": {"score": {"type": "number"}, "reasoning": {"type": "string"}},
            "required": ["score", "reasoning"],
            "additionalProperties": False,
        },
    },
}


def _base_url(region: str, override: str | None) -> str:
    if override:
        return override.rstrip("/")
    return f"https://inference.generativeai.{region}.oci.oraclecloud.com/openai/v1"


def _api_key(api_key: str | None, api_key_file: str | None) -> str:
    if api_key:
        return api_key
    if api_key_file and os.path.exists(api_key_file):
        with open(api_key_file, encoding="utf-8") as handle:
            text = handle.read().strip()
        try:  # OCI generated-secret JSON shape
            data = json.loads(text)
            return data.get("key") or data.get("api_key") or data.get("value") or text
        except json.JSONDecodeError:
            return text
    return os.environ.get("OCI_GENAI_OPENAI_API_KEY", "")


def probe(base_url: str, model: str, api_key: str) -> tuple[bool, str]:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Return only the requested JSON."},
            {"role": "user", "content": "Score 1.0 with reasoning 'ok'."},
        ],
        "response_format": _PROBE_SCHEMA,
        "max_tokens": 100,
        "temperature": 0,
    }
    request = Request(f"{base_url}/chat/completions", data=json.dumps(payload).encode(), method="POST")
    request.add_header("Authorization", f"Bearer {api_key}")
    request.add_header("Content-Type", "application/json")
    try:
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode())
    except HTTPError as exc:
        return False, f"HTTP {exc.code}: {exc.read().decode()[:200]}"
    except URLError as exc:
        return False, f"connection error: {exc}"

    try:
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        if "score" in parsed and "reasoning" in parsed:
            return True, f"structured output OK: {parsed}"
        return False, f"JSON returned but missing keys: {parsed}"
    except (KeyError, IndexError, json.JSONDecodeError) as exc:
        return False, f"non-structured response: {exc}"


def main() -> int:
    parser = argparse.ArgumentParser(description="OCI GenAI structured-output preflight for Langfuse judging")
    parser.add_argument("--region", default=os.environ.get("OCI_REGION", "us-phoenix-1"))
    parser.add_argument("--model", default=os.environ.get("STUDIO_JUDGE_MODEL", "meta.llama-3.3-70b-instruct"))
    parser.add_argument("--base-url", help="override the OpenAI-compatible base URL")
    parser.add_argument("--api-key", help="OCI GenAI OpenAI-compatible API key")
    parser.add_argument("--api-key-file", help="path to a file/JSON containing the API key")
    args = parser.parse_args()

    base_url = _base_url(args.region, args.base_url)
    api_key = _api_key(args.api_key, args.api_key_file)
    if not api_key:
        print("No API key (use --api-key / --api-key-file / OCI_GENAI_OPENAI_API_KEY).", file=sys.stderr)
        return 2

    ok, detail = probe(base_url, args.model, api_key)
    print(f"[{'PASS' if ok else 'FAIL'}] {args.model} @ {base_url}: {detail}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
