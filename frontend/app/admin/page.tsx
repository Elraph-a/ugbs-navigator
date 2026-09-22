"use client";

import { useEffect, useState } from "react";
import { analytics, ApiError } from "@/lib/api";
import type { Dashboard, GapGroup, GapLoop } from "@/lib/types";
import { DemandOverTime, RankedBars } from "@/components/Charts";
import { Alert, Chart, Check, Doc, Office, Shield } from "@/components/Icons";

export default function AdminPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<{ message: string; hint?: string } | null>(null);

  useEffect(() => {
    analytics()
      .then(setData)
      .catch((exception) =>
        setError(
          exception instanceof ApiError
            ? { message: exception.message, hint: exception.hint }
            : { message: "Could not load the analytics." },
        ),
      );
  }, []);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto w-full max-w-[54rem] px-5 py-10 sm:px-8">
        {error ? (
          <div className="rise rounded-md border border-oxide/30 bg-oxide-soft p-5">
            <p className="flex items-center gap-2 text-[0.9375rem] font-semibold text-oxide">
              <Alert className="size-4" /> {error.message}
            </p>
            {error.hint && (
              <p className="pt-2 text-[0.8125rem] leading-relaxed text-muted tabular">
                {error.hint}
              </p>
            )}
          </div>
        ) : !data ? (
          <div className="space-y-3" aria-busy>
            {[38, 88, 64].map((width) => (
              <div
                key={width}
                className="h-4 animate-pulse rounded-sm bg-sunk"
                style={{ width: `${width}%` }}
              />
            ))}
            <span className="sr-only">Loading service analytics</span>
          </div>
        ) : (
          <Report data={data} />
        )}
      </div>
    </div>
  );
}

function Report({ data }: { data: Dashboard }) {
  const { summary, deflection, forecast, source_freshness: freshness } = data;
  const peak = data.weekly_demand.totals.indexOf(Math.max(...data.weekly_demand.totals));
  // The first gap that has an action to take — "nothing to publish" groups such
  // as prediction requests are not the headline.
  const topGap = data.knowledge_gaps.find((g) => g.key !== "prediction");
  const loop = data.gap_loop;

  return (
    <div className="rise">
      <header>
        <span className="mb-4 grid size-10 place-items-center rounded-md bg-accent-soft text-accent">
          <Chart className="size-5" />
        </span>
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1">
          <h1 className="text-[clamp(1.5rem,3.4vw,2rem)] font-bold leading-tight tracking-[-0.025em]">
            Service demand
          </h1>
          <p className="text-[0.75rem] text-faint tabular">
            {summary.date_range[0]?.slice(0, 10)} to {summary.date_range[1]?.slice(0, 10)}
          </p>
        </div>
        <p className="max-w-[66ch] pt-3 text-[0.9375rem] leading-relaxed text-muted">
          Every enquiry put to the Navigator, including the ones it could not answer.
          The refusals are the useful half: they are the only record the School has of
          what students ask that nothing published covers.
        </p>
      </header>

      <p className="mt-5 flex gap-2.5 rounded-md border border-amber/25 bg-amber-soft px-4 py-3 text-[0.8125rem] leading-relaxed text-amber">
        <Alert className="mt-px size-4 shrink-0" />
        <span>
          <strong className="font-semibold tabular">
            {summary.simulated.toLocaleString()} of {summary.total.toLocaleString()}
          </strong>{" "}
          enquiries here are simulated from a modelled semester, generated for the
          prototype.{" "}
          {summary.live === 1 ? "One is real." : `${summary.live.toLocaleString()} are real.`}{" "}
          Every row, simulated or real, was routed and escalated by the live system
          rather than labelled by hand.
        </span>
      </p>

      <section className="mt-8 border-t border-line pt-6">
        <p className="max-w-[58ch] text-[1.1875rem] leading-[1.5] tracking-[-0.01em]">
          The Navigator answers{" "}
          <strong className="font-bold text-accent tabular">
            {Math.round(deflection.rate * 100)}%
          </strong>{" "}
          of enquiries outright.{" "}
          {loop && (
            <>
              Before the five missing procedures were written, that figure was{" "}
              <strong className="font-bold text-oxide tabular">
                {Math.round((1 - loop.before.rate) * 100)}%
              </strong>
              .{" "}
            </>
          )}
          {topGap && (
            <>
              The largest remaining gap: <strong className="font-semibold">{topGap.label.toLowerCase()}</strong>.
            </>
          )}
        </p>
      </section>

      <Panel
        icon={<Doc className="size-4" />}
        title="What to publish next"
        decision="Decides which documents the administrative unit should write first, and which unanswered questions need no document at all."
      >
        <p className="max-w-[68ch] pb-4 text-[0.875rem] leading-relaxed text-muted">
          Every question the Navigator could not answer, grouped first by the reason it
          went unanswered, since each reason calls for a different action, and then by
          what was asked. This list exists only because the system refuses rather than
          guessing.
        </p>

        {data.knowledge_gaps.length === 0 ? (
          <p className="rounded-md border border-line bg-surface p-4 text-[0.875rem] text-muted">
            Nothing unanswered yet.
          </p>
        ) : (
          <ol className="space-y-3">
            {data.knowledge_gaps.map((gap, i) => (
              <GapCard key={gap.key} gap={gap} index={i} />
            ))}
          </ol>
        )}
      </Panel>

      {loop && <LoopPanel loop={loop} />}

      <Panel
        icon={<Chart className="size-4" />}
        title="When the desk gets busy"
        decision="Decides when to open extra service windows and when to send notices ahead of a peak."
      >
        <div className="rounded-md border border-line bg-surface p-4 shadow-[var(--shadow-sm)]">
          <DemandOverTime
            weeks={data.weekly_demand.weeks}
            totals={data.weekly_demand.totals}
            forecastWeeks={forecast.weeks}
            forecastValues={forecast.values}
          />
        </div>
        <p className="max-w-[68ch] pt-3 text-[0.8125rem] leading-relaxed text-muted">
          Demand peaked in{" "}
          <span className="font-semibold tabular">{data.weekly_demand.weeks[peak]}</span> at{" "}
          <span className="font-semibold tabular">{data.weekly_demand.totals[peak]}</span>{" "}
          enquiries. The dashed line projects {forecast.values.length} weeks ahead by{" "}
          {forecast.method}.
        </p>
        {forecast.caveat && (
          <p className="pt-1.5 text-[0.75rem] leading-relaxed text-amber">
            {forecast.caveat}
          </p>
        )}
      </Panel>

      <div className="mt-10 grid gap-x-10 gap-y-10 md:grid-cols-2">
        <section>
          <PanelHead
            icon={<Chat />}
            title="What students ask about"
            decision="Decides which topics need clearer published guidance."
          />
          <RankedBars
            rows={data.demand_by_category.map((row) => ({
              label: row.category.replace(/_/g, " "),
              value: row.enquiries,
              sub: `${Math.round(row.escalation_rate * 100)}% unmet`,
              alert: row.escalation_rate > 0.5,
            }))}
          />
          <p className="pt-2 text-[0.75rem] leading-relaxed text-faint">
            Bars in oxide are topics where more than half of enquiries could not be
            answered from published sources.
          </p>
        </section>

        <section>
          <PanelHead
            icon={<Office />}
            title="Where the work lands"
            decision="Decides how to allocate staff across offices."
          />
          <RankedBars
            rows={data.office_load.map((row) => ({
              label: row.office,
              value: row.enquiries,
              sub: `${Math.round(row.share * 100)}%`,
            }))}
            accent="var(--muted)"
          />
        </section>
      </div>

      <Panel
        icon={<Shield className="size-4" />}
        title="How much of this rests on old paper"
        decision="Decides which documents to send for review first."
      >
        <p className="max-w-[68ch] text-[0.875rem] leading-relaxed text-muted">
          Of {freshness.answers_with_dated_sources.toLocaleString()} answers citing a
          dated source,{" "}
          <strong className="font-semibold text-amber tabular">
            {freshness.answers_citing_stale_sources.toLocaleString()} (
            {Math.round(freshness.stale_share * 100)}%)
          </strong>{" "}
          rest on a document published before {freshness.stale_before}. The College
          handbook the Business School relies on is dated 2017, so a student can be
          given a procedure that has since moved.
        </p>

        <dl className="mt-4 flex flex-wrap gap-2">
          {Object.entries(freshness.by_year).map(([year, count]) => {
            const stale = Number(year) < freshness.stale_before;
            return (
              <div
                key={year}
                className={`rounded-md border px-3 py-2 ${
                  stale
                    ? "border-amber/25 bg-amber-soft"
                    : "border-line bg-surface"
                }`}
              >
                <dt className="text-[0.6875rem] font-medium text-faint">{year}</dt>
                <dd
                  className={`text-[1.0625rem] font-semibold tabular ${
                    stale ? "text-amber" : "text-accent"
                  }`}
                >
                  {count.toLocaleString()}
                </dd>
              </div>
            );
          })}
        </dl>
      </Panel>

      <p className="mt-12 border-t border-line pt-4 text-[0.75rem] leading-relaxed text-faint">
        No enquiry here can be traced to a student. Identifiers are stripped before
        storage and no session, device or account is recorded.
      </p>
    </div>
  );
}

function GapCard({ gap, index }: { gap: GapGroup; index: number }) {
  return (
    <li
      className="slip overflow-hidden rounded-md border border-line bg-surface shadow-[var(--shadow-sm)]"
      style={{ animationDelay: `${index * 45}ms` }}
    >
      <div className="flex gap-3 p-3.5">
        <span className="grid size-6 shrink-0 place-items-center rounded-full bg-sunk text-[0.6875rem] font-semibold text-muted tabular">
          {index + 1}
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-[0.875rem] font-semibold leading-snug">{gap.label}</p>
          <p className="pt-1 text-[0.8125rem] leading-relaxed text-muted">
            <span className="font-medium text-ink">Action: </span>
            {gap.action}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-[1.0625rem] font-semibold tabular">{gap.volume}</p>
          <p className="text-[0.6875rem] text-faint tabular">
            {Math.round(gap.share_of_gaps * 100)}% of gaps
          </p>
        </div>
      </div>

      {gap.themes.length > 0 && (
        <ul className="divide-y divide-line-soft border-t border-line-soft bg-sunk/30">
          {gap.themes.slice(0, 5).map((theme) => (
            <li key={theme.theme} className="flex gap-3 py-2 pl-12 pr-3.5">
              <div className="min-w-0 flex-1">
                <p className="text-[0.8125rem] leading-snug first-letter:uppercase">{theme.theme}</p>
                <p className="truncate pt-0.5 text-[0.75rem] text-faint">
                  e.g. “{theme.examples[0]}”
                </p>
              </div>
              <span className="shrink-0 pt-0.5 text-[0.8125rem] font-medium text-muted tabular">
                {theme.volume}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}

function CompareBar({
  label,
  rate,
  count,
  colour,
}: {
  label: string;
  rate: number;
  count: number;
  colour: string;
}) {
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="w-12 shrink-0 text-[0.75rem] font-medium text-muted">{label}</span>
      <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-sunk">
        <div
          className="h-full rounded-full"
          // A 3% bar is barely a sliver; a minimum width keeps it visible as a bar.
          style={{ width: `${Math.max(rate * 100, 1.5)}%`, background: colour }}
        />
      </div>
      <span className="w-24 shrink-0 text-right text-[0.8125rem] tabular">
        <strong className="font-semibold">{Math.round(rate * 100)}%</strong>{" "}
        <span className="text-faint">({count.toLocaleString()})</span>
      </span>
    </div>
  );
}

/**
 * The decision loop, closed: the register named gaps, the gaps were filled,
 * and unanswered enquiries fell. Recomputed from the data every time rather
 * than quoted, and explicit that the filling was done with synthetic documents.
 */
function LoopPanel({ loop }: { loop: GapLoop }) {
  const beforeThemes = loop.before.gaps
    .flatMap((group) => group.themes.map((theme) => ({ ...theme, group: group.key })))
    .sort((a, b) => b.volume - a.volume)
    .slice(0, 6);

  return (
    <Panel
      icon={<Check className="size-4" />}
      title="Did publishing them work?"
      decision="Decides whether writing the documents the register asks for is worth the effort."
    >
      <p className="max-w-[68ch] pb-4 text-[0.875rem] leading-relaxed text-muted">
        The same simulated semester of {loop.questions.toLocaleString()} enquiries,
        routed twice: against the catalogue as it stood before the project team wrote
        the missing procedures the register pointed to, and against it now.
      </p>

      <div className="rounded-md border border-line bg-surface p-4 shadow-[var(--shadow-sm)]">
        <p className="label pb-2 text-faint">Unanswered enquiries</p>
        <CompareBar
          label="Before"
          rate={loop.before.rate}
          count={loop.before.escalated}
          colour="var(--oxide)"
        />
        <CompareBar
          label="After"
          rate={loop.after.rate}
          count={loop.after.escalated}
          colour="var(--accent)"
        />
      </div>

      <div className="mt-6 grid gap-x-10 gap-y-8 md:grid-cols-2">
        <section>
          <h3 className="pb-2 text-[0.875rem] font-semibold">What the register said before</h3>
          <RankedBars
            rows={beforeThemes.map((theme) => ({
              label: theme.theme,
              value: theme.volume,
              alert: theme.group === "unpublished",
            }))}
          />
        </section>
        <section>
          <h3 className="pb-2 text-[0.875rem] font-semibold">Closed by</h3>
          <RankedBars
            rows={loop.closed_by.map((closed) => ({
              label: closed.service,
              value: closed.enquiries,
              sub: closed.synthetic ? "illustrative" : undefined,
            }))}
          />
        </section>
      </div>

      {loop.rerouted.map((move) => (
        <p key={move.from + move.to} className="pt-4 text-[0.75rem] leading-relaxed text-faint">
          {move.enquiries} questions the old catalogue sent to “{move.from}” now go to “
          {move.to}”, such as “{move.example}”. That means the “before” figure for “
          {move.from}” overstates its demand by that many.
        </p>
      ))}

      <p className="mt-4 flex gap-2.5 rounded-md border border-amber/25 bg-amber-soft px-4 py-3 text-[0.8125rem] leading-relaxed text-amber">
        <Alert className="mt-px size-4 shrink-0" />
        <span>
          The procedures that closed these gaps were written by the project team, not
          published by the University. What this demonstrates is the mechanism: the
          register names a gap, the gap is filled, and unanswered enquiries fall. In
          practice, the University would have to publish them.
        </span>
      </p>
    </Panel>
  );
}

function Chat() {
  return <Doc className="size-4" />;
}

function PanelHead({
  icon,
  title,
  decision,
}: {
  icon: React.ReactNode;
  title: string;
  decision: string;
}) {
  return (
    <div className="pb-3">
      <div className="flex items-center gap-2">
        <span className="text-accent">{icon}</span>
        <h2 className="text-[1.0625rem] font-semibold leading-snug tracking-[-0.015em]">
          {title}
        </h2>
      </div>
      <p className="max-w-[56ch] pt-1 text-[0.8125rem] leading-relaxed text-faint">
        {decision}
      </p>
    </div>
  );
}

function Panel({
  icon,
  title,
  decision,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  decision: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-10">
      <PanelHead icon={icon} title={title} decision={decision} />
      {children}
    </section>
  );
}

