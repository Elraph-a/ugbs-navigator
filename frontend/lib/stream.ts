import type { AnswerResponse, ChatMessage } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export interface AgentStep {
  type: "step";
  id: string;
  label: string;
  detail?: string | null;
  confidence?: number;
  pending?: boolean;
  tone?: "verified" | "refused";
}

export type AgentEvent =
  | AgentStep
  | { type: "delta"; text: string }
  | { type: "done"; response: AnswerResponse }
  | { type: "error"; message: string; hint?: string };

/**
 * Send the conversation and yield the reply's events as they arrive: the
 * agent's steps, then the answer text piece by piece, then the final record.
 *
 * EventSource only does GET, and a conversation belongs in a body rather than a
 * URL, so the SSE frames are parsed off a streamed POST instead.
 */
export async function* chatStream(
  messages: ChatMessage[],
  signal?: AbortSignal,
): AsyncGenerator<AgentEvent> {
  let response: Response;

  try {
    response = await fetch(`${BASE}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages }),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) return;
    yield {
      type: "error",
      message: "Cannot reach the Navigator service.",
      // A free hosted backend sleeps when unused and takes a minute to wake;
      // locally, the likely cause is simply that the server is not running.
      hint: BASE.includes("localhost")
        ? `Start it with: uvicorn backend.app.main:app --port 8000  (expected at ${BASE})`
        : "The service may be waking up after a quiet period. Try again in a minute.",
    };
    return;
  }

  if (response.status === 429) {
    yield {
      type: "error",
      message: "Too many questions in a short time.",
      hint: "Please wait a minute and try again.",
    };
    return;
  }

  if (!response.ok || !response.body) {
    yield {
      type: "error",
      message: `The service returned ${response.status}.`,
      hint: (await response.text().catch(() => "")).slice(0, 240) || undefined,
    };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE frames are separated by a blank line; a partial frame stays buffered.
      const frames = buffer.split("\n\n");
      buffer = frames.pop() ?? "";

      for (const frame of frames) {
        const line = frame.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        try {
          yield JSON.parse(line.slice(6)) as AgentEvent;
        } catch {
          // A malformed frame should not kill the stream.
        }
      }
    }
  } catch (error) {
    // Stopping mid-answer is the student's choice, not a failure.
    if (signal?.aborted) return;
    throw error;
  }
}
