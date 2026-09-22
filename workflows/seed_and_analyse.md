# Workflow: Seed enquiry history and regenerate analytics

**Objective.** Give the dashboard a semester of enquiries to analyse, and refresh
the figures used in the report.

```powershell
..\AI_Lab\Scripts\python.exe tools\seed_enquiries.py --reset          # 1,200 enquiries, 16 weeks
..\AI_Lab\Scripts\python.exe tools\seed_enquiries.py --count 2000     # more volume
```

`--reset` deletes existing simulated rows only. Real logged enquiries are never
touched.

## How the simulated data is made — say this in the report

- **Question text** comes from templates per enquiry type with slot fills, so
  wording varies the way real enquiries do.
- **Volume follows the academic calendar**: registration peaks in the opening weeks,
  examinations and results at the end, transcripts and graduation after results.
- **Routing is not invented.** Every generated question runs through the real
  `core.router`, so the categories, offices and services on the dashboard are the
  ones the live system produces.
- **Escalation is not invented either.** A question escalates when the catalogue says
  the service is undocumented, when it asks for a year we do not hold, or when the
  router cannot place it — the same three rules the live agent applies.
- **Retrieval is skipped.** Running the embedding model 1,200 times would take about
  twenty minutes on this machine and changes no field the dashboard reads.

Rows are flagged `simulated = 1`, and the dashboard states the split at the top of
the report rather than blending simulated and real data silently.

## Reading the dashboard

Each panel names the decision it supports. If a panel cannot name one, it should be
removed rather than kept for decoration.

The **knowledge-gap register** is the one to lead with. It clusters the enquiries the
system refused (TF-IDF, k-means) and ranks them by how many students hit each gap.
It is an output the School cannot produce today, and it exists only because the
system refuses rather than guessing.

## Things learned

- **k=6 produced one useless mega-cluster** of 359 items. Raising to k=10 and adding
  `min_df=2`, `max_df=0.5` and `sublinear_tf` to the vectoriser separated them —
  `max_df` is what removes the "how do i / where do i" boilerplate that was pulling
  unrelated enquiries together.
- **Top TF-IDF terms overlap.** Unigrams and the bigrams containing them both score
  highly, so themes read "service, counselling service, counselling". The theme
  builder now drops any term already covered by one it kept.
- **Show cluster members nearest the centroid**, not the first three. An
  unrepresentative example makes an administrator distrust the whole cluster, and
  they would be right to.
- **A high escalation rate is a finding, not a failure.** Roughly a third of common
  enquiries have no published procedure to index. That is the problem this project
  set out to describe.
