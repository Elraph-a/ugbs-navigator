"use client";

/**
 * A very small markdown renderer for the model's answers.
 *
 * The model writes paragraphs, numbered steps, bullets, **bold** and [1] style
 * citations — nothing more. A full markdown library would be a dependency, a
 * bundle and an install step for every teammate, to render four constructs.
 *
 * It re-renders on every streamed piece, so it must cope with half-written
 * text: an unclosed "**bo" simply shows as text until its closing marker lands.
 */

type Block =
  | { kind: "p"; lines: string[] }
  | { kind: "ol" | "ul"; items: string[] };

const ORDERED = /^\s*(\d+)[.)]\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const ONLY_CITATIONS = /^\s*(\[\d+\]\s*)+$/;

// Marks where the streaming cursor goes. A private-use character, so it cannot
// collide with anything the model writes.
export const CARET = "";

// The model sometimes emits OpenAI browsing syntax, 【1†L1-L4】 or 【2】. The server
// normalises the final text, but mid-stream the raw form would flash on screen.
const ODD_CITATION = /【\s*(\d+)\s*(?:†[^】]*)?】/g;

export function normaliseCitations(text: string) {
  return text.replace(ODD_CITATION, "[$1]").replace(/\]\s*\[/g, "] [");
}

/**
 * Draw the cedi sign at the regular weight, even inside bold.
 *
 * Archivo has the glyph at every weight, but its semibold and bold versions
 * shorten the stroke to a small tail under the letter. At body size that reads
 * as a plain "C" — "GHC30" on a fee — while the regular weight's full stroke
 * reads unmistakably as ₵. Measured, not guessed: see the zoomed comparison in
 * .impeccable/review/cedi-zoom.png.
 */
export function withCedi(text: string, keyPrefix = "c"): React.ReactNode {
  if (!text.includes("₵")) return text;
  return text.split("₵").flatMap((part, i) =>
    i === 0
      ? [part]
      : [
          <span key={`${keyPrefix}${i}`} className="cedi">
            ₵
          </span>,
          part,
        ],
  );
}

function parse(text: string): Block[] {
  const blocks: Block[] = [];

  for (const raw of text.split("\n")) {
    const line = raw.trimEnd();
    const last = blocks[blocks.length - 1];

    if (!line.trim()) {
      // A blank line closes whatever was open.
      if (last?.kind === "p" && last.lines.length) blocks.push({ kind: "p", lines: [] });
      continue;
    }

    const ordered = line.match(ORDERED);
    if (ordered) {
      if (last?.kind === "ol") last.items.push(ordered[2]);
      else blocks.push({ kind: "ol", items: [ordered[2]] });
      continue;
    }

    const bullet = line.match(BULLET);
    if (bullet) {
      if (last?.kind === "ul") last.items.push(bullet[1]);
      else blocks.push({ kind: "ul", items: [bullet[1]] });
      continue;
    }

    if (last?.kind === "p") last.lines.push(line);
    else blocks.push({ kind: "p", lines: [line] });
  }

  const kept = blocks.filter((b) => (b.kind === "p" ? b.lines.length : b.items.length));

  // A line holding nothing but "[1]" renders as a lonely chip floating under the
  // answer. It belongs to whatever came before it, so it is folded back in.
  const merged: Block[] = [];
  for (const block of kept) {
    const text = block.kind === "p" ? block.lines.join(" ") : "";
    const previous = merged[merged.length - 1];
    if (block.kind === "p" && ONLY_CITATIONS.test(text.replace(CARET, "")) && previous) {
      if (previous.kind === "p") previous.lines.push(text.trim());
      else previous.items[previous.items.length - 1] += ` ${text.trim()}`;
      continue;
    }
    merged.push(block);
  }
  return merged;
}

/** Render **bold**, [1] citation chips and the streaming cursor inside a line. */
function Inline({ text }: { text: string }) {
  const parts = text
    .split(new RegExp(`(\\*\\*[^*]+\\*\\*|\\[\\d+\\]|${CARET})`, "g"))
    .filter(Boolean);

  return (
    <>
      {parts.map((part, i) => {
        if (part === CARET) {
          return <span key={i} className="caret" aria-hidden />;
        }
        if (/^\*\*[^*]+\*\*$/.test(part)) {
          return (
            <strong key={i} className="font-semibold">
              {withCedi(part.slice(2, -2), `b${i}`)}
            </strong>
          );
        }
        if (/^\[\d+\]$/.test(part)) {
          return (
            <sup
              key={i}
              className="ml-0.5 inline-flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-soft px-1 text-[0.625rem] font-semibold text-accent-ink tabular"
              title="Cited source. See Sources below."
            >
              {part.slice(1, -1)}
            </sup>
          );
        }
        return <span key={i}>{withCedi(part, `t${i}`)}</span>;
      })}
    </>
  );
}

export function Prose({ text, streaming = false }: { text: string; streaming?: boolean }) {
  const shown = normaliseCitations(text).trimEnd() + (streaming ? CARET : "");
  const blocks = parse(shown);

  return (
    <div className="space-y-3 text-[0.9375rem] leading-[1.65]">
      {blocks.map((block, i) => {
        if (block.kind === "p") {
          return (
            <p key={i}>
              <Inline text={block.lines.join(" ")} />
            </p>
          );
        }

        if (block.kind === "ol") {
          return (
            <ol key={i} className="space-y-2.5">
              {block.items.map((item, j) => (
                <li key={j} className="flex gap-3">
                  <span className="mt-px grid size-5 shrink-0 place-items-center rounded-full bg-accent-soft text-[0.6875rem] font-semibold text-accent-ink tabular">
                    {j + 1}
                  </span>
                  <span className="flex-1">
                    <Inline text={item} />
                  </span>
                </li>
              ))}
            </ol>
          );
        }

        return (
          <ul key={i} className="space-y-2">
            {block.items.map((item, j) => (
              <li key={j} className="flex gap-3">
                <span className="mt-[9px] size-1.5 shrink-0 rounded-full bg-accent" />
                <span className="flex-1">
                  <Inline text={item} />
                </span>
              </li>
            ))}
          </ul>
        );
      })}
    </div>
  );
}
