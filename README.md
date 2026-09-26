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

Backend startup takes a few seconds: it loads the embedding model at boot so the
first question is not slow. Wait for `Application startup complete`. `GET /health`
reports `"status": "degraded"` if vector search is unavailable — rebuild the index
with `tools/build_index.py --from-chunks`.

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
| `ADMIN_PASSWORD` | — | opens `/admin`; the API refuses the analytics without it |

Local model inference was measured at 1–3 minutes per answer on the target hardware
(i5-7200U, no usable GPU) and is not the default.

## Deploy

The API runs on Render's free tier (`render.yaml`); the frontend on Vercel.

- **Render:** New → Blueprint → this repository. Enter `GROQ_API_KEY` when asked,
  `ADMIN_PASSWORD` (anything you choose; the dashboard refuses to open without it),
  and `CORS_ORIGINS` (the Vercel address) once the frontend exists. The build installs
  dependencies, embeds the passages and seeds the simulated semester.
- **Vercel:** import the repository with root directory `frontend/` and set
  `NEXT_PUBLIC_API_BASE` to the Render URL.

The free tier sleeps after 15 minutes idle; a scheduled request to `/health` every
10 minutes keeps it awake. Its disk is not persistent: enquiries logged on the
hosted API are lost on restart or redeploy.

Embeddings use the ONNX build of all-MiniLM-L6-v2 bundled with Chroma rather than
PyTorch, so the server fits in 512 MB (about 280 MB measured).

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
  model. A change that lets a model originate one of these facts is a defect.
- Refusal is a designed behaviour, not an error path. It produces the knowledge-gap
  analytics. Treat a change that makes refusal less likely as a regression until
  proven otherwise.
- Enquiries are redacted before storage and carry no user identifier.
