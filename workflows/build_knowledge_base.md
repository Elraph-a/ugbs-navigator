# Workflow: Build the knowledge base

**Objective.** Turn the raw documents into a searchable index: read → chunk →
embed → persist.

**When to run.** After `collect_sources.py`, after editing anything in
`data/synthetic/`, and after changing chunk sizes in `core/chunking.py`.

## Steps

```powershell
..\AI_Lab\Scripts\python.exe tools\build_index.py --dry-run   # chunk + report, no embedding
..\AI_Lab\Scripts\python.exe tools\build_index.py             # full build
```

Run `--dry-run` first. It is fast and shows the chunk count and category histogram
without spending a minute on embedding.

## Outputs

- `data/chunks.json` — every chunk with full provenance (also used by keyword search)
- `data/chroma/` — the persisted vector index

## What a healthy build looks like

- **~200–400 chunks** across 14 documents.
- **No single document above ~40%** of the corpus. If one dominates, it probably
  needs an `extract` block in `data/sources.yaml`.
- **Every administrative category represented.** Categories at zero are real gaps —
  either a source is missing, or the procedure genuinely is not published. The second
  case is a finding, not a bug: it is what the knowledge-gap register reports.

## Edge cases and things learned

- **Embedding is the slow step** — about 70 seconds for 218 chunks on the demo
  laptop (i5-7200U, CPU only, roughly 3 chunks/sec). It is a build cost, not a
  request cost: at query time only the question is embedded, in 20–50 ms.
- **The first run downloads the model** (~85 MB to `~/.cache/huggingface`). Running
  this in a background shell can stall silently on that download. Run it in the
  foreground the first time so you can see progress.
- **Rebuild, never patch.** The tool deletes `data/chroma/` and rebuilds. A stale
  collection keeps serving chunks from documents that have been removed.
- **Cleaning is deliberately light.** `core/ingest.py` preserves case, punctuation
  and paragraph breaks. Do not reuse MiniGPT's `clean_text`, which lowercases and
  collapses everything — right for training a language model, wrong here, because
  "Room D2" and "GH₵30" have to come back out exactly as they went in.
- **Synthetic documents need front matter.** A file in `data/synthetic/` without
  `provenance: synthetic` is skipped with a message rather than indexed as real.
