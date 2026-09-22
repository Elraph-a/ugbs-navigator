"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { chatStream, type AgentStep } from "@/lib/stream";
import type { AnswerResponse, ChatMessage } from "@/lib/types";
import { AgentSteps } from "./AgentSteps";
import { Material } from "./Answer";
import { Prose } from "./Prose";
import { Alert, ArrowUp, Chat, Copy, Mark, Shield } from "./Icons";

interface Turn {
  id: number;
  question: string;
  /** The reply as it has arrived so far. */
  text: string;
  steps: AgentStep[];
  response: AnswerResponse | null;
  error: { message: string; hint?: string } | null;
  running: boolean;
  stopped: boolean;
}

// How many earlier exchanges travel with each message. Matches the server's
// window, so nothing is sent that would only be thrown away.
const HISTORY_EXCHANGES = 4;

const SUGGESTIONS = [
  {
    q: "How do I request an official transcript?",
    hint: "Then ask “how much is it?”",
  },
  {
    q: "I am a UGBS graduate student, I need my transcript urgently and I graduated in 1994",
    hint: "Three procedures at once",
  },
  {
    q: "I want to take a semester off. What should I do?",
    hint: "Deferment, in plain words",
  },
  {
    q: "What will the 2027/2028 MBA fee be?",
    hint: "Watch it decline to guess",
  },
];

export function Conversation() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  const busyRef = useRef(false);
  const turnsRef = useRef<Turn[]>([]);
  const abortRef = useRef<AbortController | null>(null);
  const nextId = useRef(0);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);

  turnsRef.current = turns;

  /* Follow the stream only while the reader is already near the bottom.
     Yanking someone back down while they are reading an earlier answer is the
     rudest thing a chat interface can do. */
  const stickToBottom = useRef(true);

  const onScroll = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    stickToBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
  }, []);

  useEffect(() => {
    // Instant, not smooth: a smooth scroll restarted on every streamed word
    // never catches up, and the text visibly outruns the viewport.
    const el = scrollerRef.current;
    if (el && stickToBottom.current) el.scrollTop = el.scrollHeight;
  });

  const send = useCallback(async (text: string) => {
    const question = text.trim();
    if (!question || busyRef.current) return;

    busyRef.current = true;
    setBusy(true);
    setDraft("");
    stickToBottom.current = true;

    // The conversation so far, as the server needs it. Failed and empty turns
    // are left out: a reply that never arrived is not something to refer back to.
    const history: ChatMessage[] = turnsRef.current
      .filter((turn) => turn.text.trim() && !turn.error)
      .slice(-HISTORY_EXCHANGES)
      .flatMap((turn) => [
        { role: "user" as const, content: turn.question },
        { role: "assistant" as const, content: turn.text },
      ]);

    const id = nextId.current++;
    setTurns((previous) => [
      ...previous,
      {
        id,
        question,
        text: "",
        steps: [],
        response: null,
        error: null,
        running: true,
        stopped: false,
      },
    ]);

    const patch = (change: (turn: Turn) => Turn) =>
      setTurns((previous) => previous.map((turn) => (turn.id === id ? change(turn) : turn)));

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      for await (const event of chatStream(
        [...history, { role: "user", content: question }],
        controller.signal,
      )) {
        if (event.type === "step") {
          patch((turn) => {
            // A step arrives twice: once pending, once resolved. Replace in place
            // so the row settles rather than the list growing a duplicate.
            const steps = [...turn.steps];
            const existing = steps.findIndex((s) => s.id === event.id && s.pending);
            if (existing >= 0) steps[existing] = event;
            else steps.push(event);
            return { ...turn, steps };
          });
        } else if (event.type === "delta") {
          patch((turn) => ({ ...turn, text: turn.text + event.text }));
        } else if (event.type === "done") {
          patch((turn) => ({
            ...turn,
            // The server's final text has its citations normalised; prefer it.
            text: event.response.answer ?? turn.text,
            response: event.response,
            running: false,
          }));
        } else if (event.type === "error") {
          patch((turn) => ({
            ...turn,
            error: { message: event.message, hint: event.hint },
            running: false,
          }));
        }
      }
    } catch {
      patch((turn) => ({
        ...turn,
        error: { message: "The connection dropped before the answer finished." },
      }));
    }

    patch((turn) => ({
      ...turn,
      running: false,
      stopped: controller.signal.aborted,
    }));
    abortRef.current = null;
    busyRef.current = false;
    setBusy(false);
    inputRef.current?.focus();
  }, []);

  const stop = useCallback(() => abortRef.current?.abort(), []);

  // ?q= asks on load, so the demo cases are links rather than retyping.
  useEffect(() => {
    const preset = new URLSearchParams(window.location.search).get("q");
    if (preset) send(preset);
    return () => abortRef.current?.abort();
  }, [send]);

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollerRef} onScroll={onScroll} data-scroller className="flex-1 overflow-y-auto">
        {/* With nothing asked yet, centre the greeting rather than leaving a
            void between it and the composer. */}
        <div
          className={`mx-auto flex w-full max-w-[46rem] flex-col px-4 py-8 sm:px-6 ${
            turns.length === 0 ? "min-h-full justify-center" : ""
          }`}
        >
          {turns.length === 0 ? (
            <Welcome onPick={send} />
          ) : (
            <div className="space-y-9">
              {turns.map((turn) => (
                <TurnView key={turn.id} turn={turn} />
              ))}
            </div>
          )}
          <div ref={endRef} className="h-4" />
        </div>
      </div>

      <Composer
        draft={draft}
        setDraft={setDraft}
        onSend={send}
        onStop={stop}
        busy={busy}
        inputRef={inputRef}
        started={turns.length > 0}
      />
    </div>
  );
}

/* ---------------------------------------------------------------- turn ---- */

function TurnView({ turn }: { turn: Turn }) {
  const { response } = turn;
  const writing = turn.text.length > 0;
  const conversational = Boolean(response?.conversational);

  return (
    // data-* hooks let the browser checks find a turn and know when it is done.
    <div className="rise" data-turn data-running={turn.running ? "true" : "false"}>
      <div className="flex justify-end pb-4">
        <p className="max-w-[85%] whitespace-pre-wrap rounded-lg rounded-br-sm bg-ink px-4 py-2.5 text-[0.9375rem] leading-relaxed text-white shadow-[var(--shadow-sm)]">
          {turn.question}
        </p>
      </div>

      <div className="flex gap-3">
        <span className="mt-0.5 hidden shrink-0 text-accent sm:block">
          <Mark className="size-7" />
        </span>

        <div className="min-w-0 flex-1 pt-0.5">
          <AgentSteps steps={turn.steps} running={turn.running} writing={writing} />

          {/* Small talk has no steps, so something has to show the reply is coming. */}
          {turn.running && !writing && turn.steps.length === 0 && <Typing />}

          {writing && (
            <div data-reply>
              <Prose text={turn.text} streaming={turn.running} />
            </div>
          )}

          {turn.stopped && (
            <p className="pt-2 text-[0.75rem] text-faint">Stopped.</p>
          )}

          {turn.error && (
            <div className="rise mt-2 rounded-md border border-oxide/30 bg-oxide-soft p-4">
              <p className="flex items-center gap-2 text-[0.875rem] font-semibold text-oxide">
                <Alert className="size-4" />
                {turn.error.message}
              </p>
              {turn.error.hint && (
                <p className="pt-1.5 text-[0.8125rem] leading-relaxed text-muted tabular">
                  {turn.error.hint}
                </p>
              )}
            </div>
          )}

          {response && !conversational && <Material response={response} />}

          {response && !turn.running && !conversational && (
            <TurnFooter response={response} text={turn.text} />
          )}
        </div>
      </div>
    </div>
  );
}

function Typing() {
  return (
    <span className="flex h-6 items-center gap-1" aria-label="Writing a reply">
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="dot size-1.5 rounded-full bg-accent"
          style={{ animationDelay: `${i * 180}ms` }}
        />
      ))}
    </span>
  );
}

function TurnFooter({ response, text }: { response: AnswerResponse; text: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-2">
      <button
        type="button"
        onClick={() => {
          // Citation markers mean nothing outside this page.
          navigator.clipboard?.writeText(text.replace(/\s*\[\d+\]/g, ""));
          setCopied(true);
          setTimeout(() => setCopied(false), 1600);
        }}
        className="press hoverable flex items-center gap-1.5 rounded-sm px-2 py-1 text-[0.75rem] font-medium text-muted"
      >
        <Copy className="size-3.5" />
        {copied ? "Copied" : "Copy answer"}
      </button>

      {response.escalated && (
        <span className="flex items-center gap-1.5 text-[0.75rem] text-oxide">
          <Alert className="size-3.5" />
          No published source, so this was recorded for the admin team
        </span>
      )}

      {response.pii_redacted.length > 0 && (
        <span className="flex items-center gap-1.5 text-[0.75rem] text-amber">
          <Shield className="size-3.5" />
          Removed before storing: {response.pii_redacted.join(", ")}
        </span>
      )}

      <span className="ml-auto text-[0.75rem] text-faint tabular">
        {response.elapsed_ms < 100
          ? `${response.elapsed_ms}ms`
          : `${(response.elapsed_ms / 1000).toFixed(1)}s`}
      </span>
    </div>
  );
}

/* --------------------------------------------------------------- welcome -- */

function Welcome({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div>
      <span className="pop mb-5 grid size-11 place-items-center rounded-md bg-accent-soft text-accent">
        <Chat className="size-5" />
      </span>

      <h1 className="rise max-w-[20ch] text-[clamp(1.75rem,4.5vw,2.375rem)] font-bold leading-[1.1] tracking-[-0.03em] text-balance">
        Ask me anything about UGBS admin.
      </h1>

      <p
        className="rise max-w-[54ch] pt-3 text-[0.9375rem] leading-relaxed text-muted"
        style={{ animationDelay: "60ms" }}
      >
        Ask about registration, transcripts, fees, results, deferment, ID cards or
        graduation in your own words, and ask follow-ups too. I keep track of the
        conversation.
        Every answer comes from published University of Ghana documents with the
        source shown, and when nothing published covers it, I will say so rather
        than guess.
      </p>

      <div className="mt-8 grid gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((suggestion, index) => (
          <button
            key={suggestion.q}
            type="button"
            onClick={() => onPick(suggestion.q)}
            className="press rise group rounded-md border border-line bg-surface p-3.5 text-left shadow-[var(--shadow-sm)] hover:border-accent/40 hover:shadow-[var(--shadow-md)]"
            style={{ animationDelay: `${120 + index * 55}ms` }}
          >
            <span className="block text-[0.875rem] font-medium leading-snug">
              {suggestion.q}
            </span>
            <span className="block pt-1 text-[0.75rem] text-faint">{suggestion.hint}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* -------------------------------------------------------------- composer -- */

function Composer({
  draft,
  setDraft,
  onSend,
  onStop,
  busy,
  inputRef,
  started,
}: {
  draft: string;
  setDraft: (value: string) => void;
  onSend: (value: string) => void;
  onStop: () => void;
  busy: boolean;
  inputRef: React.RefObject<HTMLTextAreaElement | null>;
  started: boolean;
}) {
  // Grow with the content instead of scrolling inside two rows.
  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [draft, inputRef]);

  return (
    <div className="shrink-0 bg-gradient-to-t from-canvas via-canvas to-transparent pb-4 pt-2">
      <div className="mx-auto w-full max-w-[46rem] px-4 sm:px-6">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (!busy) onSend(draft);
          }}
          className="rounded-lg border border-line bg-surface shadow-[var(--shadow-md)] transition-shadow focus-within:border-accent/40 focus-within:shadow-[var(--shadow-lg)]"
        >
          <textarea
            ref={inputRef}
            rows={1}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (!busy) onSend(draft);
              }
            }}
            placeholder={started ? "Ask a follow-up…" : "Ask about any administrative procedure…"}
            className="block max-h-[180px] w-full resize-none bg-transparent px-4 pt-3.5 text-[0.9375rem] leading-relaxed outline-none placeholder:text-faint"
          />

          <div className="flex items-center justify-between gap-3 px-3 pb-3 pt-1">
            <p className="pl-1 text-[0.6875rem] leading-tight text-faint">
              Do not include your student ID. Identifiers are removed before anything
              is stored.
            </p>

            {busy ? (
              <button
                type="button"
                onClick={onStop}
                aria-label="Stop the answer"
                className="press grid size-8 shrink-0 place-items-center rounded-sm bg-ink text-white"
              >
                <span className="block size-2.5 rounded-[2px] bg-white" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!draft.trim()}
                aria-label="Send"
                className="press grid size-8 shrink-0 place-items-center rounded-sm bg-accent text-white disabled:bg-line disabled:text-faint"
              >
                <ArrowUp className="size-4" />
              </button>
            )}
          </div>
        </form>

        <p className="pt-2 text-center text-[0.6875rem] text-faint">
          Decision support, not an official ruling. Confirm with the office before acting
          on a deadline or a fee.
        </p>
      </div>
    </div>
  );
}
