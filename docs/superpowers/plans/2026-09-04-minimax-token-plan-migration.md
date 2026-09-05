# MiniMax Token Plan Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the runtime DeepSeek configuration with MiniMax Token Plan through the existing OpenAI-compatible HTTP client.

**Architecture:** Keep the existing `OpenAILLM` transport and per-agent profile split. Rename the runtime environment variables to `MINIMAX_*`, use `https://api.minimax.cn/v1` as the Token Plan OpenAI-compatible base URL, and use `MiniMax-M3` for both chat and reasoner profiles. Store the supplied credential only in the ignored local `.env` file.

**Tech Stack:** Python, `aiohttp`, existing OpenAI-compatible chat-completions client, `pytest`, `python-dotenv`.

**Spec:** MiniMax official Token Plan OpenAI-compatible configuration: base URL `https://api.minimax.cn/v1`, model `MiniMax-M3`, bearer API key.

## Global Constraints

- Do not add a new SDK or provider dependency.
- Do not print, commit, or place the credential in tracked source, tests, docs, logs, or frontend code.
- Keep `LLM_PROVIDER=openai`; MiniMax is consumed through the existing OpenAI-compatible transport.
- Keep the existing `chat` and `reasoner` profile behavior; only provider credentials, endpoint, and model names change.
- Do not rewrite historical evidence or handoff documents merely because they mention the former provider.

---

### Task 1: Add a configuration regression test

**Files:**
- Create: `ai-service/tests/test_minimax_config.py`

**Interfaces:**
- Consumes: `app.services.llm_service.OpenAILLM`.
- Produces: A test that fails while `OpenAILLM` still reads `DEEPSEEK_*` and passes after it reads `MINIMAX_*`.

- [x] **Step 1: Write the failing test**

```python
from app.services.llm_service import OpenAILLM


def test_openai_compatible_client_reads_minimax_defaults(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_BASE_URL", raising=False)
    monkeypatch.delenv("DEEPSEEK_MODEL_CHAT", raising=False)
    monkeypatch.setenv("MINIMAX_API_KEY", "minimax-test-token")
    monkeypatch.setenv("MINIMAX_BASE_URL", "https://api.minimax.cn/v1")
    monkeypatch.setenv("MINIMAX_MODEL_CHAT", "MiniMax-M3")

    llm = OpenAILLM(use_mock=True)

    assert llm.base_url == "https://api.minimax.cn/v1"
    assert llm.model == "MiniMax-M3"
    assert llm.api_key == "minimax-test-token"
```

- [x] **Step 2: Run the test to verify it fails for the old configuration**

Run: `python -m pytest ai-service/tests/test_minimax_config.py -q`

Expected: FAIL because the current client reads `DEEPSEEK_*` and falls back to the DeepSeek endpoint/model.

### Task 2: Switch the runtime provider settings

**Files:**
- Modify: `ai-service/app/services/llm_service.py:8-12,104-122,149-257,294-304,560-578`
- Modify: `ai-service/.env.example:1-14`
- Modify: `ai-service/.env:24-37` (ignored local file only)

**Interfaces:**
- Consumes: `MINIMAX_API_KEY`, `MINIMAX_BASE_URL`, `MINIMAX_MODEL_CHAT`, and `MINIMAX_MODEL_REASONER`.
- Produces: Existing `create_llm()`, `OpenAILLM`, and all existing profiles using MiniMax without call-site changes.

- [x] **Step 1: Change the provider comments and model configuration names**

Use these runtime values in `llm_service.py`:

```python
_MM_KEY = os.getenv("MINIMAX_API_KEY", "")
_MM_BASE = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1")
_MODEL_CHAT = os.getenv("MINIMAX_MODEL_CHAT", "MiniMax-M3")
_MODEL_REASONER = os.getenv("MINIMAX_MODEL_REASONER", "") or _MODEL_CHAT
```

Update the `OpenAILLM` fallback reads and missing-credential error to the corresponding `MINIMAX_*` names. Keep the class name because it describes the wire protocol, not a vendor.

- [x] **Step 2: Update the tracked environment template**

The relevant block in `.env.example` must be:

```dotenv
LLM_PROVIDER=openai
MINIMAX_API_KEY=your_minimax_token_plan_key_here
MINIMAX_BASE_URL=https://api.minimax.cn/v1
MINIMAX_MODEL_CHAT=MiniMax-M3
MINIMAX_MODEL_REASONER=MiniMax-M3
```

- [x] **Step 3: Update the ignored local environment**

Set the existing local `.env` to the same MiniMax endpoint and model names, and put the user-supplied Token Plan credential only in `MINIMAX_API_KEY`. Do not print the value during verification.

### Task 3: Verify the migration and credential hygiene

**Files:**
- Test: `ai-service/tests/test_minimax_config.py`
- Inspect: `ai-service/app/services/llm_service.py`, `ai-service/.env.example`, `ai-service/.gitignore`

**Interfaces:**
- Consumes: The migrated runtime configuration.
- Produces: Evidence that mocked client construction uses MiniMax and no credential appears in tracked files.

- [x] **Step 1: Run the focused regression test**

Run: `python -m pytest ai-service/tests/test_minimax_config.py -q`

Expected: 1 passed.

- [x] **Step 2: Run the existing LLM/config and quality-gate tests**

Run: `python -m pytest ai-service/tests/test_llm_service.py ai-service/tests/test_resource_quality_gate.py -q`

Expected: all tests pass without real network calls.

- [x] **Step 3: Check tracked-source references and secret hygiene**

Run: `git grep -n -I -E 'DEEPSEEK_API_KEY|DEEPSEEK_BASE_URL|DEEPSEEK_MODEL_|sk-cp-' -- ':!ai-service/.env'` and `git diff --check`.

Expected: no credential or new DeepSeek runtime environment reference in tracked files; whitespace check exits 0.

- [x] **Step 4: Optionally verify the MiniMax `/models` endpoint without printing the token**

Use a one-off request with the local `MINIMAX_API_KEY` and report only the HTTP status and whether `MiniMax-M3` is listed. Do not save the response or echo authorization headers.
