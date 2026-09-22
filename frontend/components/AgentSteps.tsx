"use client";

import { useState } from "react";
import type { AgentStep } from "@/lib/stream";
import { Alert, Check, Chevron, Doc, Pen, Route, Search, Shield } from "./Icons";

function glyphFor(id: string) {
  if (id.startsWith("search")) return Search;
  if (id.startsWith("write")) return Pen;
  if (id.startsWith("verify") || id === "scope") return Shield;
  if (id === "route" || id === "plan") return Route;
  return Doc;
}

/**
 * The agent's work, as it happens.
 *
 * These are the real events the backend emits while the loop runs, not a
 * progress animation. While the request is live the list stays open; once it
 * finishes it collapses to a single line, because nobody rereads the trace of a
 * question that was answered.
 */
export function AgentSteps({
  steps,
  running,
  writing = false,
}: {
  steps: AgentStep[];
  running: boolean;
  /** True once answer text has started arriving. */
  writing?: boolean;
}) {
  const [open, setOpen] = useState(false);
  if (!steps.length) return null;

  // Open while the agent is still finding material; folded to one line the
  // moment it starts writing, so the answer — not the trace — has the reader.
  const expanded = (running && !writing) || open;

  // While running, the in-flight step is the headline and the list shows what is
  // already done. Printing it in both places just reads as a stutter.
  const inFlight = steps.find((step) => step.pending);
  const visible = running ? steps.filter((step) => !step.pending) : steps;
  // The number of procedures checked, not the number of sub-steps.

  const searched = steps.filter((s) => s.id.startsWith("search")).length;
  const elapsedLabel = running
    ? inFlight?.label ?? steps[steps.length - 1]?.label ?? "Working"
    : `Checked ${searched} document set${searched === 1 ? "" : "s"}`;

  return (
    <div className="mb-3">
      <button
        type="button"
        onClick={() => (!running || writing) && setOpen((value) => !value)}
        disabled={running && !writing}
        className="press flex items-center gap-2 text-left disabled:cursor-default"
        aria-expanded={expanded}
      >
        {running ? (
          <span className="flex gap-1" aria-hidden>
            {[0, 1, 2].map((i) => (
              <span
                key={i}
                className="dot size-1.5 rounded-full bg-accent"
                style={{ animationDelay: `${i * 180}ms` }}
              />
            ))}
          </span>
        ) : (
          <Check className="size-3.5 text-accent" />
        )}

        <span
          className={`text-[0.8125rem] font-medium ${running ? "working" : "text-muted"}`}
        >
          {elapsedLabel}
        </span>

        {(!running || writing) && (
          <Chevron
            className={`size-3.5 text-faint transition-transform duration-200 ${open ? "rotate-90" : ""}`}
          />
        )}
      </button>

      <span className="sr-only" aria-live="polite">
        {running ? elapsedLabel : "Answer ready"}
      </span>

      {expanded && (
        <ol className="mt-2.5 space-y-2 border-l border-line pl-4">
          {visible.map((step, index) => {
            const Glyph = glyphFor(step.id);
            const tone =
              step.tone === "refused"
                ? "text-oxide"
                : step.tone === "verified"
                  ? "text-accent"
                  : "text-faint";

            return (
              <li
                key={`${step.id}-${index}`}
                className="slip flex items-start gap-2.5"
                style={{ animationDelay: `${Math.min(index, 6) * 45}ms` }}
              >
                <span className={`mt-[3px] shrink-0 ${tone}`}>
                  {step.pending ? (
                    <span className="dot block size-3 rounded-full border-[1.6px] border-current" />
                  ) : step.tone === "refused" ? (
                    <Alert className="size-3.5" />
                  ) : (
                    <Glyph className="size-3.5" />
                  )}
                </span>

                <span className="min-w-0 flex-1">
                  <span
                    className={`block text-[0.8125rem] leading-snug ${
                      step.pending ? "text-faint" : "text-muted"
                    }`}
                  >
                    {step.label}
                  </span>
                  {step.detail && (
                    <span
                      className={`block pt-0.5 text-[0.75rem] leading-snug tabular ${
                        step.tone === "refused" ? "text-oxide" : "text-faint"
                      }`}
                    >
                      {step.detail}
                    </span>
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
