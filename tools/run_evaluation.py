"""Measure the system against tests/gold_questions.yaml.

    ..\\AI_Lab\\Scripts\\python.exe tools\\run_evaluation.py
    ..\\AI_Lab\\Scripts\\python.exe tools\\run_evaluation.py --no-log   # do not pollute the enquiry log

Reports four numbers, and the last two matter most:

  Routing accuracy    did the enquiry reach the office that owns it
  Service accuracy    did it reach the right procedure variant
  Refusal precision   of the questions it MUST refuse, how many did it refuse
  Answer rate         of the questions it should answer, how many it answered

A system that answers everything scores well on answer rate and is dangerous.
A system that refuses everything scores perfectly on refusal precision and is
useless. Both are reported so neither can be optimised alone.

Results are written to docs/evaluation-results.md for the report.
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config
from core.agent import answer as run_agent
from core.generate import llm_available


def degraded(response: dict) -> str | None:
    """Why this response did not come from the full system, or None if it did.

    A first held-out run was taken while the model host was unreachable: every
    answer was the extractive fallback, the median latency was 55 ms, and three
    "leaks" turned out to be the fallback path rather than the system. Numbers
    from a run like that describe the outage, so the run is marked invalid.
    """
    if not llm_available():
        return None  # an extractive-only run is measured as such, not as degraded
    provider = response.get("provider", "")
    if provider not in (config.settings.llm_provider, "conversational"):
        return f"answer: {provider}"
    triage = response.get("triage", "")
    if triage.startswith("failed") or triage == "no model":
        return f"triage: {triage}"
    return None


def evaluate(log: bool, gold_file: str = "gold_questions.yaml", pace: float = 0.0) -> dict:
    from core import store

    gold = yaml.safe_load((config.TESTS / gold_file).read_text(encoding="utf-8"))

    in_scope = gold["in_scope"]
    out_scope = gold["out_of_scope"]

    routing_hits = 0
    routing_total = 0
    service_hits = 0
    service_total = 0
    answered = 0
    latencies: list[int] = []
    failures: list[dict] = []
    rows: list[dict] = []
    degraded_runs: list[dict] = []

    print(f"In-scope enquiries ({len(in_scope)})\n")

    for case in in_scope:
        if pace:
            time.sleep(pace)
        response = run_agent(case["q"])
        if log:
            store.log_enquiry(response, simulated=False)
        latencies.append(response["elapsed_ms"])

        office_id = (response.get("office") or {}).get("id")
        service_ids = {
            section["service"]["id"]
            for section in response["sections"]
            if section.get("service")
        }

        routing_total += 1
        office_ok = office_id == case["expected_office"]
        routing_hits += int(office_ok)

        service_ok = True
        if "expected_service" in case:
            service_total += 1
            service_ok = case["expected_service"] in service_ids
            service_hits += int(service_ok)

        # `declined` covers every way the system can decline: no verified source,
        # a prediction request, or a question outside University administration.
        if not response.get("declined", response["escalated"]):
            answered += 1

        mark = "ok  " if office_ok and service_ok else "MISS"
        why = degraded(response)
        if why:
            degraded_runs.append({"question": case["q"], "why": why})
        rows.append(
            {
                "set": "in scope",
                "question": case["q"],
                "expected": case["expected_office"]
                + (f" / {case['expected_service']}" if "expected_service" in case else ""),
                "got": (office_id or "-")
                + (f" / {', '.join(sorted(service_ids))}" if service_ids else ""),
                "result": "correct" if office_ok and service_ok else "miss",
                "declined": bool(response.get("declined", response["escalated"])),
                "ms": response["elapsed_ms"],
            }
        )
        print(f"  {mark} {case['q'][:58]:<58} -> {office_id or '-'}{'  [DEGRADED: ' + why + ']' if why else ''}")

        if not (office_ok and service_ok):
            failures.append(
                {
                    "question": case["q"],
                    "expected_office": case["expected_office"],
                    "got_office": office_id,
                    "expected_service": case.get("expected_service"),
                    "got_services": sorted(service_ids),
                }
            )

    print(f"\nOut-of-scope enquiries ({len(out_scope)}) — every one must be refused\n")

    refused = 0
    leaks: list[dict] = []

    for case in out_scope:
        if pace:
            time.sleep(pace)
        response = run_agent(case["q"])
        if log:
            store.log_enquiry(response, simulated=False)
        latencies.append(response["elapsed_ms"])

        why = degraded(response)
        if why:
            degraded_runs.append({"question": case["q"], "why": why})
        flag = f"  [DEGRADED: {why}]" if why else ""

        declined = bool(response.get("declined", response["escalated"]))
        rows.append(
            {
                "set": "out of scope",
                "question": case["q"],
                "expected": "declined",
                "got": "declined" if declined else "answered",
                "result": "correct" if declined else "leak",
                "declined": declined,
                "ms": response["elapsed_ms"],
            }
        )
        if declined:
            refused += 1
            print(f"  ok   {case['q'][:58]:<58} refused{flag}")
        else:
            print(f"  LEAK {case['q'][:58]:<58} ANSWERED{flag}")
            leaks.append({"question": case["q"], "why": case["why"]})

    return {
        "routing_accuracy": routing_hits / max(routing_total, 1),
        "routing_hits": routing_hits,
        "routing_total": routing_total,
        "service_accuracy": service_hits / max(service_total, 1),
        "service_hits": service_hits,
        "service_total": service_total,
        "refusal_precision": refused / max(len(out_scope), 1),
        "refused": refused,
        "out_of_scope_total": len(out_scope),
        "answer_rate": answered / max(len(in_scope), 1),
        "answered": answered,
        "in_scope_total": len(in_scope),
        "median_latency_ms": int(statistics.median(latencies)) if latencies else 0,
        "p90_latency_ms": int(sorted(latencies)[int(len(latencies) * 0.9)]) if latencies else 0,
        "failures": failures,
        "leaks": leaks,
        "rows": rows,
        "degraded": degraded_runs,
        "provider": config.settings.llm_provider,
        "models": (
            f"{config.settings.groq_model} (answers), {config.settings.groq_fast_model} (triage)"
            if config.settings.llm_provider == "groq"
            else None
        ),
    }


def write_report(results: dict, gold_file: str, out_file: str, pace: float) -> None:
    total = results["routing_total"] + results["out_of_scope_total"]
    degraded_count = len(results["degraded"])
    lines = [
        "# Evaluation results",
        "",
        f"Produced by `tools/run_evaluation.py` against `tests/{gold_file}` "
        f"on {time.strftime('%Y-%m-%d %H:%M')}.",
        f"Provider: `{results['provider']}`"
        + (f" — {results['models']}" if results["models"] else "")
        + (f". Paced {pace:g}s between questions." if pace else "."),
        "",
    ]
    if degraded_count:
        lines += [
            f"> **This run is not valid.** {degraded_count} of {total} responses did not "
            "come from the full system (the model was unreachable or rate-limited, and "
            "a fallback answered). Re-run before quoting these numbers.",
            "",
            *[f"> - {d['question']} — {d['why']}" for d in results["degraded"]],
            "",
        ]
    else:
        lines += [
            f"Every one of the {total} responses came from the full system: the model "
            "answered, and triage ran wherever it was needed.",
            "",
        ]
    lines += [
        "| Measure | Result | What it means |",
        "| --- | --- | --- |",
        f"| Routing accuracy | **{results['routing_accuracy']:.0%}** "
        f"({results['routing_hits']}/{results['routing_total']}) | "
        "Reached the office that owns the enquiry. |",
        f"| Service accuracy | **{results['service_accuracy']:.0%}** "
        f"({results['service_hits']}/{results['service_total']}) | "
        "Reached the correct procedure variant, where one is correct. |",
        f"| Refusal precision | **{results['refusal_precision']:.0%}** "
        f"({results['refused']}/{results['out_of_scope_total']}) | "
        "Refused every enquiry it has no verified source for. |",
        f"| Answer rate | **{results['answer_rate']:.0%}** "
        f"({results['answered']}/{results['in_scope_total']}) | "
        "Answered enquiries a published source does cover. |",
        f"| Median latency | {results['median_latency_ms']:,} ms | |",
        f"| 90th percentile latency | {results['p90_latency_ms']:,} ms | |",
        "",
        "Answer rate and refusal precision are reported together on purpose. A system "
        "that answers everything scores 100% on the first and is unsafe; one that refuses "
        "everything scores 100% on the second and is useless. Neither number means "
        "anything alone.",
        "",
    ]

    if results["leaks"]:
        lines += [
            "## Questions that should have been refused but were answered",
            "",
            "These are the failures that matter. Each one is a student being given "
            "something the system cannot support.",
            "",
            "| Question | Why it should have been refused |",
            "| --- | --- |",
            *[f"| {leak['question']} | {leak['why']} |" for leak in results["leaks"]],
            "",
        ]
    else:
        lines += ["Every out-of-scope enquiry was refused.", ""]

    if results["failures"]:
        lines += [
            "## Routing failures",
            "",
            "| Question | Expected | Got |",
            "| --- | --- | --- |",
            *[
                f"| {f['question']} | {f['expected_office']}"
                f"{' / ' + f['expected_service'] if f['expected_service'] else ''} | "
                f"{f['got_office']}{' / ' + ', '.join(f['got_services']) if f['got_services'] else ''} |"
                for f in results["failures"]
            ],
            "",
        ]

    lines += [
        "## Every question",
        "",
        "| Set | Question | Expected | Got | Result | ms |",
        "| --- | --- | --- | --- | --- | --- |",
        *[
            f"| {r['set']} | {r['question']} | {r['expected']} | {r['got']}"
            f"{' (declined)' if r['declined'] and r['set'] == 'in scope' else ''} | "
            f"{r['result']} | {r['ms']:,} |"
            for r in results["rows"]
        ],
        "",
    ]

    config.DOCS.mkdir(parents=True, exist_ok=True)
    (config.DOCS / out_file).write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-log", action="store_true", help="do not write these runs to the enquiry log"
    )
    parser.add_argument(
        "--gold",
        default="gold_questions.yaml",
        help="question file in tests/ (holdout_questions.yaml for the held-out set)",
    )
    parser.add_argument(
        "--pace",
        type=float,
        default=0.0,
        help="seconds to wait between questions. The model host's free tier allows "
        "8,000 tokens a minute, so an unpaced run measures throttling, not the "
        "system; pace it to measure what one student actually experiences.",
    )
    args = parser.parse_args()

    out_file = (
        "evaluation-results.md"
        if args.gold == "gold_questions.yaml"
        else f"evaluation-{Path(args.gold).stem.replace('_questions', '')}.md"
    )

    from core.generate import warm
    from core.retrieve import _embedder, load_chunks

    # The server loads the embedding model and opens its model connections at
    # start-up, so the measurement must too. Without this the first question
    # carries the ~19s embedding load and reads as a 44s answer.
    load_chunks()
    _embedder().encode(["warm up"])
    warm()

    started = time.time()
    results = evaluate(log=not args.no_log, gold_file=args.gold, pace=args.pace)
    write_report(results, args.gold, out_file, args.pace)

    print(f"\n{'-' * 62}")
    print(f"  Routing accuracy    {results['routing_accuracy']:>6.0%}  "
          f"({results['routing_hits']}/{results['routing_total']})")
    print(f"  Service accuracy    {results['service_accuracy']:>6.0%}  "
          f"({results['service_hits']}/{results['service_total']})")
    print(f"  Refusal precision   {results['refusal_precision']:>6.0%}  "
          f"({results['refused']}/{results['out_of_scope_total']})")
    print(f"  Answer rate         {results['answer_rate']:>6.0%}  "
          f"({results['answered']}/{results['in_scope_total']})")
    print(f"  Median latency      {results['median_latency_ms']:>6,} ms")
    print(f"\n  Ran in {time.time() - started:.0f}s")
    print(f"  Written to {config.DOCS / out_file}")

    if results["degraded"]:
        print(
            f"\n  NOT VALID: {len(results['degraded'])} responses came from a fallback, "
            "not the model. Re-run with a larger --pace."
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
