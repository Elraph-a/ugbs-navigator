# UGBS Service Navigator

An administrative enquiry and service-navigation agent for University of Ghana
Business School students. A student asks a question in ordinary language; the system
answers from published University documents with citations, routes the enquiry to the
office that owns it, and refuses when it has no verified source. Every enquiry is
logged, and the logged refusals drive an analytics view showing which procedures the
School has not published.

Built for OMIS 404. Not an official University of Ghana service.

## Requirements

- Python 3.11+ — this repository uses the sibling `AI_Lab` virtual environment
- Node 20+
- No API key is needed to run it. `LLM_PROVIDER=extractive` exercises the whole
  pipeline without a model.

## Setup

```powershell
copy .env.example .env

..\AI_Lab\Scripts\python.exe tools\collect_sources.py     # fetch published sources
..\AI_Lab\Scripts\python.exe tools\build_index.py         # chunk + embed (~70s)
..\AI_Lab\Scripts\python.exe tools\seed_enquiries.py      # simulated semester for the dashboard

npm --prefix frontend install
```

## Run

```powershell
..\AI_Lab\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000

npm --prefix frontend run build
npm --prefix frontend start
```

Frontend on `http://localhost:3000`, API on `http://localhost:8000`.

Backend startup takes 60–90 seconds: it loads the embedding model at boot so the
first question is not slow. Wait for `Application startup complete`.

## Layout

```
workflows/   SOPs — read the relevant one before changing how something works
tools/       deterministic CLI scripts (collect, index, seed, evaluate)
core/        shared logic imported by both tools/ and backend/
backend/     FastAPI service
frontend/    Next.js app: /  student enquiry, /admin  service analytics
data/        sources manifest, raw documents, structured catalogue, index
docs/        architecture diagrams, evaluation results
```

`core/` holds the agent loop, retrieval, routing, generation and analytics so the
evaluation tool runs the same code the API serves.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `LLM_PROVIDER` | `extractive` | `groq`, `gemini`, `ollama` or `extractive` |
| `GROQ_API_KEY` | — | only for `groq` — https://console.groq.com/keys |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | answers; verify with `tools/check_provider.py` |
| `GROQ_FAST_MODEL` | `openai/gpt-oss-20b` | triage and follow-up rewriting |
| `GEMINI_API_KEY` | — | only for `gemini` |
| `CONFIDENCE_THRESHOLD` | `0.42` | tuned on the gold set; below this no model is called |
| `RETENTION_DAYS` | `180` | logged enquiries are purged past this |

Local model inference was measured at 1–3 minutes per answer on the target hardware
(i5-7200U, no usable GPU) and is not the default.

## Deploy

The API runs as a Hugging Face Docker Space; the frontend on Vercel.

```powershell
..\AI_Lab\Scripts\python.exe tools\deploy_backend.py --dry-run          # list what would be uploaded
..\AI_Lab\Scripts\python.exe tools\deploy_backend.py --cors https://<app>.vercel.app
```

Needs `HF_TOKEN` and `GROQ_API_KEY` in `.env`. The key is stored as a Space secret,
not uploaded. The image embeds the passages and seeds the simulated semester at
build time (`deploy/huggingface/Dockerfile`). Its disk is not persistent: enquiries
logged on the hosted API are lost when the Space restarts.

On Vercel, set the project root to `frontend/` and `NEXT_PUBLIC_API_BASE` to the
Space URL.

## Tests and evaluation

```powershell
..\AI_Lab\Scripts\python.exe -m pytest tests -q
..\AI_Lab\Scripts\python.exe tools\run_evaluation.py --no-log
```

The evaluation writes `docs/evaluation-results.md` and reports routing accuracy,
service accuracy, refusal precision and answer rate. Read the last two together:
answering everything scores perfectly on one and is unsafe; refusing everything
scores perfectly on the other and is useless.

## Things to know before changing anything

- Office names, room numbers, fees, contacts and processing times come from
  `data/structured/` or a retrieved chunk. They are never produced by a language
  model. See `CLAUDE.md` section 3.
- Refusal is a designed behaviour, not an error path. It produces the knowledge-gap
  analytics. Treat a change that makes refusal less likely as a regression until
  proven otherwise.
- Enquiries are redacted before storage and carry no user identifier.
