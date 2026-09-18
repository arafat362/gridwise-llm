# GridWise LLM

BUP CSE Fest 2026 preliminary — 24-hour campus energy scheduling with LLM note interpretation.

**Live API:** https://home-local.pure-server.com  
**Health:** https://home-local.pure-server.com/health → `{"status":"ok"}`

Endpoints:
- `GET /health`
- `POST /optimize-energy`

**Model (OpenRouter):** `openai/gpt-4.1`

---

## How it works

```
operator notes → OpenRouter LLM → guardrails → PuLP optimizer → JSON plan
```

1. **LLM** maps each note to a directive (`solar_reduction`, charge/discharge windows, reserve, grid cap, or `no_op`).
2. **Guardrails** check types, hours, and numbers before anything hits the solver.
3. **Optimizer** minimizes grid cost for the day while obeying battery rules and those directives.

---

## Run locally

```bash
cd gridwise-llm
python -m venv .venv
.\.venv\Scripts\Activate.ps1          # Windows
# source .venv/bin/activate           # Linux/macOS
pip install -r requirements.txt
copy .env.example .env                # then set OPENROUTER_API_KEY
```

Start:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
# or run.bat on Windows
```

Checks:

```bash
curl https://home-local.pure-server.com/health
python scripts/validate_optimizer.py
```

### Env vars

| Name | Required | Notes |
|------|----------|--------|
| `OPENROUTER_API_KEY` | yes | keep in `.env` only |
| `OPENROUTER_MODEL` | no | default `openai/gpt-4.1` |
| `OPENROUTER_BASE_URL` | no | `https://openrouter.ai/api/v1` |
| `LLM_TIMEOUT_SECONDS` | no | default `20` |
| `LLM_MAX_RETRIES` | no | default `2` |
| `LLM_MAX_TOKENS` | no | default `2500` |
| `APP_PORT` | no | default `8000` |

---

## Docker

```bash
docker build -t gridwise-llm:local .
docker run --rm -p 8000:8000 \
  -e OPENROUTER_API_KEY=your-key \
  -e OPENROUTER_MODEL=openai/gpt-4.1 \
  gridwise-llm:local
```

Or: `docker compose up --build`

Do not bake secrets into the image.

---

## Layout

```
app/           API + services
data/          public sample cases
scripts/       validate_optimizer.py
Dockerfile
run.bat
```

---

## Stack

FastAPI, Uvicorn, Pydantic, OpenAI SDK (OpenRouter), PuLP/CBC, httpx.
