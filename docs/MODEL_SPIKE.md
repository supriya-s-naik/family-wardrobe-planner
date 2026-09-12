# Nebius Model Integration Spike

**Date:** September 12, 2026  
**Status:** Live end-to-end generation verified

## Objective

Verify that the selected Nebius Token Factory model can:

1. Select the correct application tool and produce valid arguments.
2. Return output that follows a Pydantic-derived JSON schema.
3. Preserve stable household, event, and wardrobe item IDs.
4. Respond within an interactive-demo latency budget.

## Current configuration

- Provider: Nebius Token Factory
- Configured model: `Qwen/Qwen3-30B-A3B-Instruct-2507`
- API style: OpenAI-compatible Chat Completions
- Current documented endpoint: `https://api.tokenfactory.nebius.com/v1/`

Nebius documents both [OpenAI-compatible function calling](https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling) and [JSON-schema structured output](https://docs.tokenfactory.nebius.com/ai-models-inference/json).

## Implemented test

Run:

```powershell
uv run python scripts/smoke_test_nebius.py
```

The script performs two small calls:

1. Presents `search_wardrobe` and `get_weather`, then verifies the model selects `search_wardrobe` for a footwear request and retains `member_maya`.
2. Supplies Maya's authoritative wardrobe and the school event, then validates a generated mini outfit against a strict Pydantic schema and rejects unknown item IDs.

The script never prints the API key.

## Observed result in the Codex runtime

- Credential presence: confirmed without exposing the value.
- Model listing: passed; the account returned 24 available models.
- The original `meta-llama/Llama-3.3-70B-Instruct` workflow timed out after 120 seconds.
- The live workflow was reduced from repeated model/tool round trips to one aggregate context tool followed by one model request.
- `Qwen/Qwen3-30B-A3B-Instruct-2507` returned a complete valid plan in 49.5 seconds.
- Result: 9 event/member outfits, 1 application tool call, and 0 validation errors.

## Acceptance decision

`Qwen/Qwen3-30B-A3B-Instruct-2507` is selected for the prototype because it completed the full typed workflow within the interactive-demo latency budget. The Llama model remains a quality comparison candidate for offline evaluation, but its observed latency is unsuitable for the live demo.

## Configuration update

The project `.env` and `.env.example` now use the current endpoint:

```text
NEBIUS_BASE_URL=https://api.tokenfactory.nebius.com/v1/
```

The API key remains private and `.env` is excluded from Git.
