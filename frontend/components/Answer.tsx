"use client";

import { useState } from "react";
import type { AnswerResponse, Citation, Office, Section } from "@/lib/types";
import { Alert, Check, Chevron, Doc, Office as OfficeIcon, Shield } from "./Icons";
import { withCedi } from "./Prose";

/* ------------------------------------------------------------------ badge -- */

export function Badge({
  tone,
  children,
}: {
  tone: "verified" | "refused" | "caution";
  children: React.ReactNode;
}) {
  const tones = {
    verified: "bg-accent-soft text-accent-ink",
    refused: "bg-oxide-soft text-oxide",
    caution: "bg-amber-soft text-amber",
  } as const;

  const Glyph = tone === "verified" ? Check : Alert;

  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-[3px] text-[0.6875rem] font-semibold ${tones[tone]}`}
    >
      <Glyph className="size-3" />
      {children}
    </span>
  );
}

/* --------------------------------------------------------------- office --- */

export function OfficeCard({ office }: { office: Office }) {
  const rows: [string, React.ReactNode][] = [];

  if (office.location) rows.push(["Where", office.location]);
  if (office.postal_address) rows.push(["Post", office.postal_address]);
  if (office.phone)
    rows.push([
      "Phone",
      <a
        key="p"
        className="underline decoration-line underline-offset-2 hover:decoration-accent"
        href={`tel:${office.phone.replace(/[^+\d]/g, "")}`}
      >
        {office.phone}
      </a>,
    ]);
  if (office.email)
    rows.push([
      "Email",
      <a
        key="e"
        className="break-all underline decoration-line underline-offset-2 hover:decoration-accent"
        href={`mailto:${office.email}`}
      >
        {office.email}
      </a>,
    ]);
  if (office.hours) rows.push(["Hours", office.hours]);

  return (
    <div className="rise overflow-hidden rounded-md border border-line bg-surface shadow-[var(--shadow-sm)]">
      <div className="flex items-start gap-3 border-b border-line-soft bg-accent-soft/50 px-4 py-3">
        <span className="mt-px grid size-8 shrink-0 place-items-center rounded-sm bg-accent text-white">
          <OfficeIcon className="size-4" />
        </span>
        <div className="min-w-0">
          <p className="label text-accent-ink">Go here</p>
          <p className="pt-0.5 text-[0.9375rem] font-semibold leading-snug">
            {office.name}
          </p>
        </div>
      </div>

      <dl className="divide-y divide-line-soft px-4">
        {rows.map(([term, value]) => (
          <div key={term} className="flex gap-4 py-2.5">
            <dt className="w-14 shrink-0 text-[0.75rem] font-medium text-faint">
              {term}
            </dt>
            <dd className="min-w-0 flex-1 text-[0.8125rem] leading-relaxed tabular">
              {value}
            </dd>
          </div>
        ))}
      </dl>

      {rows.length < 3 && (
        <p className="border-t border-line-soft bg-amber-soft px-4 py-2.5 text-[0.75rem] leading-relaxed text-amber">
          The University does not publish full contact details for this office. What
          is shown is everything we could verify.
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------ citations --- */

function sourceAge(published: string) {
  const year = Number.parseInt(published.slice(0, 4), 10);
  if (!Number.isFinite(year)) return null;
  return { year, stale: year < 2020 };
}

export function Citations({ citations }: { citations: Citation[] }) {
  const [open, setOpen] = useState(false);
  if (!citations.length) return null;

  return (
    <div className="rise rounded-md border border-line bg-surface px-4 py-2.5 shadow-[var(--shadow-sm)]">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="press group flex w-full items-center gap-2 text-left"
        aria-expanded={open}
      >
        <Doc className="size-3.5 text-faint" />
        <span className="text-[0.75rem] font-medium text-muted">
          {citations.length} source{citations.length === 1 ? "" : "s"}
        </span>
        <Chevron
          className={`size-3.5 text-faint transition-transform duration-200 ${open ? "rotate-90" : ""}`}
        />
      </button>

      {open && (
        <ol className="slip mt-2.5 space-y-2 pb-1">
          {citations.map((citation) => {
            const age = sourceAge(citation.published_date);
            return (
              <li
                key={citation.index}
                className="rounded-sm bg-sunk/60 px-3 py-2 text-[0.75rem] leading-relaxed"
              >
                <p className="font-medium">
                  {citation.source_url ? (
                    <a
                      href={citation.source_url}
                      target="_blank"
                      rel="noreferrer"
                      className="underline decoration-line underline-offset-2 hover:decoration-accent"
                    >
                      {citation.doc_title}
                    </a>
                  ) : (
                    citation.doc_title
                  )}
                  {citation.section && citation.section !== citation.doc_title && (
                    <span className="font-normal text-faint"> · {citation.section}</span>
                  )}
                </p>
                <p className="flex flex-wrap items-center gap-x-2 pt-0.5 text-faint">
                  <span>{citation.publisher}</span>
                  {age && (
                    <span className={age.stale ? "text-amber" : undefined}>
                      {age.year}
                      {age.stale && " · may be superseded"}
                    </span>
                  )}
                  {citation.provenance === "synthetic" && (
                    <span className="text-amber">
                      authored by the project team
                    </span>
                  )}
                </p>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}

/* ------------------------------------------------------------- material --- */

/**
 * What sits under the answer: the verified procedures it drew on, the office to
 * visit, and the sources.
 *
 * The prose above is written by a model; everything here comes straight from
 * the catalogue and the index. Keeping them visibly separate is what lets a
 * student check the wording against the record — the grounding made visible
 * rather than merely claimed.
 */
export function Material({ response }: { response: AnswerResponse }) {
  const procedures = response.sections.filter(
    (section) => section.service && !section.refused && section.service.steps?.length,
  );
  const citations = response.citations ?? [];

  if (!procedures.length && !response.office && !citations.length) return null;

  return (
    <div className="mt-4 space-y-3">
      {procedures.map((section, index) => (
        <ProcedureMaterial key={section.service!.id} section={section} index={index} />
      ))}
      {response.office && <OfficeCard office={response.office} />}
      <Citations citations={citations} />
    </div>
  );
}

function ProcedureMaterial({ section, index }: { section: Section; index: number }) {
  const service = section.service!;
  const synthetic = service.provenance === "synthetic";

  return (
    <article
      className="pop overflow-hidden rounded-md border border-line bg-surface shadow-[var(--shadow-sm)]"
      style={{ animationDelay: `${index * 60}ms` }}
    >
      <header className="flex flex-wrap items-center gap-x-3 gap-y-2 px-4 pt-3">
        <h3 className="min-w-0 flex-1 text-[0.875rem] font-semibold leading-snug">
          {service.name}
        </h3>
        {synthetic ? (
          <Badge tone="caution">Illustrative</Badge>
        ) : (
          <Badge tone="verified">Published</Badge>
        )}
      </header>

      <div className="px-4 pb-3">
        {synthetic && (
          <p className="pt-1.5 text-[0.75rem] leading-relaxed text-amber">
            Written by the project team — no published University procedure was found
            for this. Illustrative only.
          </p>
        )}

        {service.caveat && (
          <p className="pt-1.5 text-[0.75rem] leading-relaxed text-amber">{service.caveat}</p>
        )}

        {!!service.fees?.length && (
          <FeeTable fees={service.fees} note={service.fees_note ?? null} />
        )}

        {/* The procedure the model was handed, verbatim. */}
        <VerifiedSteps steps={service.steps} />
      </div>
    </article>
  );
}

function VerifiedSteps({ steps }: { steps: string[] }) {
  const [open, setOpen] = useState(false);

  return (
    <div className="mt-4 rounded-sm border border-line-soft bg-sunk/40">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="press flex w-full items-center gap-2 px-3 py-2 text-left"
        aria-expanded={open}
      >
        <Shield className="size-3.5 shrink-0 text-accent" />
        <span className="flex-1 text-[0.75rem] font-medium text-muted">
          Verified procedure ({steps.length} steps)
        </span>
        <Chevron
          className={`size-3.5 text-faint transition-transform duration-200 ${open ? "rotate-90" : ""}`}
        />
      </button>

      {open && (
        <ol className="slip space-y-1.5 border-t border-line-soft px-3 py-2.5">
          {steps.map((step, i) => (
            <li key={i} className="flex gap-2 text-[0.75rem] leading-relaxed text-muted">
              <span className="shrink-0 text-faint tabular">{i + 1}.</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function FeeTable({
  fees,
  note,
}: {
  fees: NonNullable<Section["service"]>["fees"];
  note: string | null;
}) {
  return (
    <div className="mt-4">
      <p className="label pb-2 text-faint">Published fees</p>

      {/* On a phone the three columns wrap into unreadable stacks, so the same
          rows render as blocks instead. */}
      <ul className="space-y-2 sm:hidden">
        {fees.map((fee, i) => (
          <li key={i} className="rounded-sm border border-line px-3 py-2.5">
            <p className="text-[0.8125rem] font-medium leading-snug">{fee.mode}</p>
            <p className="pt-1 text-[0.9375rem] font-semibold tabular">
              {withCedi(fee.first_copy ?? "—")}
            </p>
            {fee.additional && (
              <p className="pt-0.5 text-[0.75rem] leading-relaxed text-muted tabular">
                Additional: {withCedi(fee.additional)}
              </p>
            )}
          </li>
        ))}
      </ul>

      <div className="hidden overflow-x-auto rounded-sm border border-line sm:block">
        <table className="w-full border-collapse text-left text-[0.8125rem]">
          <thead>
            <tr className="border-b border-line bg-sunk/70">
              <th className="px-3 py-2 font-medium text-faint">Mode</th>
              <th className="px-3 py-2 font-medium text-faint">First copy</th>
              <th className="px-3 py-2 font-medium text-faint">Additional</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line-soft">
            {fees.map((fee, i) => (
              <tr key={i}>
                <td className="px-3 py-2 leading-snug">{fee.mode}</td>
                <td className="whitespace-nowrap px-3 py-2 font-semibold tabular">
                  {withCedi(fee.first_copy ?? "—")}
                </td>
                <td className="px-3 py-2 leading-snug text-muted tabular">
                  {withCedi(fee.additional ?? "—")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {note && <p className="pt-2 text-[0.75rem] leading-relaxed text-faint">{note}</p>}
    </div>
  );
}
