# Workflow: Evaluate the system

**Objective.** Produce the numbers the report needs, and catch the one failure that
matters — the system answering something it cannot support.

```powershell
..\AI_Lab\Scripts\python.exe tools\run_evaluation.py --no-log   # does not touch the enquiry log
..\AI_Lab\Scripts\python.exe tools\run_evaluation.py            # logs the runs, so they appear on the dashboard
```

Writes `docs/evaluation-results.md`. Takes about a minute.

**Two question sets.** `tests/gold_questions.yaml` is the development set — it was
tuned against, so its scores overstate performance. `tests/holdout_questions.yaml` is
the held-out set, and its numbers are the ones the report quotes. Do not change the
system to pass a held-out question; record the miss instead.

```powershell
..\AI_Lab\Scripts\python.exe tools\run_evaluation.py --gold holdout_questions.yaml --pace 25 --no-log
```

Writes `docs/evaluation-holdout.md`, including a table of every question.

## What is measured

| Measure | Reads |
| --- | --- |
| Routing accuracy | did the enquiry reach the office that owns it |
| Service accuracy | did it reach the right procedure variant |
| **Refusal precision** | of the enquiries it must refuse, how many it refused |
| Answer rate | of the enquiries a source does cover, how many it answered |

**Read the last two together, always.** A system that answers everything scores 100%
on answer rate and is unsafe. One that refuses everything scores 100% on refusal
precision and is useless. Neither number means anything alone, and optimising either
in isolation makes the system worse.

## Interpreting a failure

- **A LEAK line is the serious one.** An out-of-scope enquiry was answered. Find out
  why before doing anything else: usually the routing confidence was high enough to
  place it, or retrieval cleared the threshold on weak evidence.
- **A MISS is a routing problem**, normally a missing alias in
  `data/structured/services.json`, or two services competing for the same words.

## Things learned

- **A run where the model was unreachable measures the outage, not the system.**
  The first held-out run happened while Groq was unreachable: every reply was the
  extractive fallback, median latency was 55 ms, and three off-topic questions were
  "answered". Each response now records `provider` (who wrote the answer) and
  `triage` (whether scope was checked). The tool marks the run **not valid** and
  exits 1 if any response came from a fallback. Never quote a run marked that way.
- **Warm retrieval, not just the model.** The first held-out run showed a 44-second
  first answer. That was the embedding model loading inside the first question —
  the server pays that at start-up. The tool now loads it before measuring, and
  `warm()` opens both Groq models, since warming only the fast triage model left
  the answer model cold.
- **Pace Groq runs.** The free tier allows 8,000 tokens a minute per model, and one
  grounded answer uses a large share of that. Unpaced, the later questions hit the
  limit and fall back. `--pace 25` keeps a run clean.
- **Separation lives in routing confidence, not retrieval confidence.** Measured on
  the gold set: genuine enquiries route at 0.86–0.98 and retrieve at 0.46–0.68;
  off-topic ones route at 0.00 and retrieve at 0.33–0.41. Retrieval alone does not
  separate them, which is why `UNROUTED_FLOOR` in `core/agent.py` requires strong
  retrieval before an unplaced enquiry may be answered from the corpus.
- **Raising `CONFIDENCE_THRESHOLD` from 0.35 to 0.42** took refusal precision from
  70% to 100% and cost one in-scope answer. That is the right side of the trade for
  this product.
- **Prediction questions are a separate failure class.** "Will I pass my exams this
  semester?" routes confidently to examinations and retrieves real examination text,
  then answers a question no document addresses. No threshold catches it;
  `PREDICTION_PATTERNS` in `core/agent.py` refuses it explicitly.
- **Alias collisions are easy to create.** Adding "what courses" to course
  information broke "how do I register for my courses". After editing aliases,
  re-run this workflow before assuming the change was an improvement.
- **A degraded run usually means the connection, not the free tier.** Three runs on
  2026-09-26 were thrown away because answers came from the extractive fallback.
  The messages said `APITimeoutError` and `APIConnectionError`, not `RateLimitError`.
  Two separate causes, both now fixed in `core/generate.py`: the SDK was allowing a
  connection five seconds to open, which a cold TLS handshake on this network
  sometimes exceeds (`timeout=httpx.Timeout(120.0, connect=20.0)`), and a dropped
  connection went straight to the fallback instead of being tried once more
  (`_once_more`). Rate-limit failover to the spare model is deliberately *not*
  retried, because waiting out a 429 makes the student wait.
- **Check the network before starting a long run.** A few `complete()` calls in a
  loop take seconds and show whether the host is answering: the first is around
  7 s on a cold connection and the rest under a second. A run that starts while
  the connection is flaky will waste fifteen minutes.
- **Both sets are worth re-running together.** The report quotes the development
  set and the held-out set side by side, so a valid held-out run beside a stale or
  invalid development run is not a fair comparison.
