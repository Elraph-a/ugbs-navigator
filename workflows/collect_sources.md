# Workflow: Collect source documents

**Objective.** Fetch every published UG/UGBS document the knowledge base depends on
into `data/raw/`, and record where each came from and when.

**When to run.** At the start of the project, when a source is added to the manifest,
and before a demo if a procedure may have changed.

## Inputs

- `data/sources.yaml` — the manifest. One entry per document: `id`, `title`, `url`,
  `category`, `publisher`, `authority`, `published_date`.

## Steps

1. Add or edit the entry in `data/sources.yaml`. Set `published_date` only if the
   document states one — leave it `null` otherwise. The dashboard measures how much
   of the corpus is undated, and a guessed date corrupts that measure.
2. Run the tool:

   ```powershell
   ..\AI_Lab\Scripts\python.exe tools\collect_sources.py
   ..\AI_Lab\Scripts\python.exe tools\collect_sources.py --only <id>     # one source
   ..\AI_Lab\Scripts\python.exe tools\collect_sources.py --refresh       # re-download all
   ```

3. Read the summary. Every source is `fetched`, `cached` or `FAILED`.
4. Rebuild the index (`workflows/build_knowledge_base.md`). New raw files change
   nothing until they are chunked and embedded.

## Outputs

- `data/raw/<id>.txt` or `<id>.pdf`
- `data/raw/sources_index.json` — provenance used by the index builder
- `data/raw/SOURCES.md` — the provenance table the report cites

## Edge cases and things learned

- **Navigation-only pages.** Several `old1.ug.edu.gh` pages return a shell whose only
  markup is the site menu. It extracts as a short block of link labels — plausible
  text that is pure navigation. The tool rejects any extraction that is ≥90% list
  items, because indexing a menu is worse than indexing nothing: retrieval will match
  a student's question against it and cite it as a source.
- **JavaScript-rendered pages** (`/academics/calendar`, `ugbs.ug.edu.gh/contact`)
  cannot be fetched with `requests`. They stay in the manifest and are recorded under
  "Could not be fetched" in `SOURCES.md` so the gap is visible. Do not delete them to
  make the run look clean.
- **`--only` merges, it does not replace.** An earlier version overwrote
  `sources_index.json` with the single fetched record, silently shrinking the
  knowledge base to one document. If you change this tool, keep the merge.
- **Documents covering more than UGBS.** The College of Humanities handbook covers
  every school in the college. Add an `extract` block with `start` and `end` markers
  so only the UGBS section is indexed; the full 1.3M characters would swamp retrieval
  with Law and Performing Arts course descriptions.
- **Fees change yearly.** When a new fee schedule is published, add it as a new
  source and update `data_year` on the `fees_schedule` service, or the coverage check
  will keep refusing the current year.
