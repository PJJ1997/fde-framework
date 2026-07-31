# LLM Environment Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move Azure OpenAI, DeepSeek, and LangSmith configuration out of source code into a root `.env` with safe loading, validation, and documentation.

**Architecture:** A focused `llm.config` module loads the root `.env` without overriding process variables and exposes typed configuration helpers. The factory, providers, and tracing initialization consume environment values through that module; `.env.example` documents the contract without secrets.

**Tech Stack:** Python 3.11, python-dotenv, unittest, unittest.mock, LangChain OpenAI.

## Global Constraints

- `.env` remains ignored by Git and contains the current local runtime values.
- `.env.example` contains placeholders and non-sensitive defaults only.
- Process environment variables take precedence over `.env`.
- API keys must never appear in logs, exceptions, README, tests, or committed files.
- Missing required provider configuration fails when that provider is created.
- LangSmith configuration remains optional and must not block application startup.
- Existing unrelated working-tree changes must be preserved.

---

### Task 1: Central Configuration Loading and Validation

**Files:**
- Create: `llm/config.py`
- Create: `tests/llm/__init__.py`
- Create: `tests/llm/test_config.py`

**Interfaces:**
- Produces: `load_environment(env_path: Optional[Path] = None) -> None`
- Produces: `get_env(name: str, default: Optional[str] = None, required: bool = False) -> str`
- Produces: `get_float_env(name: str, default: float) -> float`

- [ ] **Step 1: Write failing tests**

Test that a temporary `.env` is loaded, an existing process variable wins over the file, required empty values raise `ValueError` containing only the variable name, and invalid float values raise a clear `ValueError`.

- [ ] **Step 2: Verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.llm.test_config -v
```

Expected: import failure because `llm.config` does not exist.

- [ ] **Step 3: Implement the minimal configuration module**

Use `Path(__file__).resolve().parents[1] / ".env"` as the default file and `load_dotenv(dotenv_path=..., override=False)`. Strip values, reject required empty strings, and convert float configuration with a variable-name-only error.

- [ ] **Step 4: Verify GREEN**

Run the same unittest command and expect all configuration tests to pass.

---

### Task 2: Migrate Factory and Providers

**Files:**
- Modify: `llm/factory.py`
- Modify: `llm/providers/deepseek.py`
- Modify: `llm/providers/azure_openai.py`
- Create: `tests/llm/test_factory.py`
- Create: `tests/llm/test_providers.py`

**Interfaces:**
- Consumes: `load_environment`, `get_env`, and `get_float_env` from `llm.config`
- Preserves: `create_llm(provider: Optional[str] = None) -> BaseChatModel`
- Preserves: `create_deepseek_llm() -> ChatOpenAI`
- Preserves: `create_azure_openai_llm() -> AzureChatOpenAI`

- [ ] **Step 1: Write failing factory and provider tests**

Patch the provider constructors at their module boundary and verify:

- `LLM_PROVIDER` selects the default provider.
- The explicit `provider` argument takes precedence.
- Azure consumes `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`, and `LLM_TEMPERATURE`.
- DeepSeek consumes `DEEPSEEK_API_KEY`, `DEEPSEEK_MODEL`, `DEEPSEEK_BASE_URL`, and `LLM_TEMPERATURE`.
- Missing required values raise before a network client is usable.

- [ ] **Step 2: Verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.llm.test_factory tests.llm.test_providers -v
```

Expected: failures because the current factory and providers still use hardcoded values.

- [ ] **Step 3: Implement environment-backed factory and providers**

Load the environment in `create_llm`, read `LLM_PROVIDER` with `azure_openai` as the non-sensitive default, and replace all provider literals with validated environment values. Keep only model/base URL/API version/temperature defaults that contain no credentials or environment-specific Azure endpoint.

- [ ] **Step 4: Verify GREEN**

Run the same unittest command and expect all tests to pass.

---

### Task 3: Load LangSmith Configuration and Remove Committed Secrets

**Files:**
- Modify: `tracing/langsmith.py`
- Modify: `README.md`
- Create: `.env.example`
- Create locally, ignored: `.env`
- Create: `tests/tracing/__init__.py`
- Create: `tests/tracing/test_langsmith.py`

**Interfaces:**
- Consumes: `load_environment()` before reading `LANGSMITH_*`
- Preserves: existing tracing enable/disable behavior

- [ ] **Step 1: Write a failing tracing test**

Use an isolated temporary `.env`, clear relevant process variables, reload the tracing module, and verify its setup sees `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT` from the file without exposing the key.

- [ ] **Step 2: Verify RED**

Run:

```bash
.venv/bin/python -m unittest tests.tracing.test_langsmith -v
```

Expected: failure because tracing reads the process environment before the central loader is called.

- [ ] **Step 3: Implement tracing loading and safe configuration files**

Call `load_environment()` before tracing checks. Add `.env.example` with placeholders. Create ignored `.env` with the current local Azure, DeepSeek, and LangSmith values. Replace the README credential literal with `${DEEPSEEK_API_KEY}` or an `.env` setup example.

- [ ] **Step 4: Scan tracked and untracked source safely**

Search for credential-shaped assignments and ensure no committed file contains the known exposed values. Do not print `.env` contents.

- [ ] **Step 5: Verify targeted tests**

Run:

```bash
.venv/bin/python -m unittest tests.llm.test_config tests.llm.test_factory tests.llm.test_providers tests.tracing.test_langsmith -v
```

Expected: all pass.

---

### Task 4: Full Verification and Handoff

**Files:**
- Verify all modified files

**Interfaces:**
- Produces: a runnable application whose LLM and tracing settings come from `.env`

- [ ] **Step 1: Run the full test suite**

```bash
.venv/bin/python -m unittest discover -s tests -t . -v
```

- [ ] **Step 2: Compile and import the application**

```bash
.venv/bin/python -m compileall -q agents app context llm tracing
.venv/bin/python -c 'from app.main import app; from llm.factory import create_llm; print(app.title)'
```

- [ ] **Step 3: Validate diffs and secret hygiene**

```bash
git diff --check
git status --short
```

Confirm `.env` is ignored, `.env.example` is visible, no secret is staged or printed, and existing unrelated modifications remain intact.

- [ ] **Step 4: Report mandatory credential rotation**

Tell the user that moving credentials prevents future source exposure but does not revoke already exposed credentials or remove them from Git history; Azure OpenAI, DeepSeek, and LangSmith keys must be rotated.
