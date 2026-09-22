# Workflow: Run the prototype

**Objective.** Get both halves running and confirm they talk to each other.

## Prerequisites

Run once, in order, before the first start:

```powershell
..\AI_Lab\Scripts\python.exe tools\collect_sources.py
..\AI_Lab\Scripts\python.exe tools\build_index.py
..\AI_Lab\Scripts\python.exe tools\seed_enquiries.py
```

Copy `.env.example` to `.env`. `LLM_PROVIDER=extractive` needs no API key and
exercises the whole pipeline.

## Start

```powershell
# backend — from the project root
..\AI_Lab\Scripts\python.exe -m uvicorn backend.app.main:app --port 8000

# frontend — production build, which is what the demo should use
npm --prefix frontend run build
npm --prefix frontend start
```

Backend on `http://localhost:8000`, frontend on `http://localhost:3000`.

## Confirm it works

```powershell
Invoke-WebRequest http://localhost:8000/health -UseBasicParsing | Select -Expand Content
```

Then open `http://localhost:3000` and run the three demo cases.

## Demo links

`?q=` asks on load, so the three cases are bookmarkable rather than retyped in
front of an audience:

- Normal — `/?q=How do I request an official transcript?`
- Complex — `/?q=I am a UGBS graduate student, I need my transcript urgently and I graduated in 1994`
- Failure — `/?q=What will the 2027/2028 MBA fee be?` then open `/admin`

## Edge cases and things learned

- **Backend startup takes 60–90 seconds.** It warms the embedding model on purpose,
  so the first student question is not an 80-second hang. Wait for
  `Application startup complete` before opening the browser.
- **Use `npm start`, not `npm run dev`, for the demo.** The dev server's watcher and
  HMR cost RAM the demo laptop cannot spare (5.5 GB free before Chroma, the model,
  Node and a browser).
- **Start the backend before the browser.** If the frontend loads first it shows a
  "cannot reach the service" panel until you reload.
- **PowerShell:** `Start-Process npm` fails with "not a valid Win32 application" —
  launch `node node_modules\next\dist\bin\next start` instead. And
  `Invoke-WebRequest` needs `-UseBasicParsing` in a non-interactive shell.
- **If the network fails mid-demo,** set `LLM_PROVIDER=extractive` and restart the
  backend. Every procedure, fee, office and citation still works, because those come
  from the catalogue and the index, not from a model.
