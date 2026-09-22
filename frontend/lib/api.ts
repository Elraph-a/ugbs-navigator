import type { AnswerResponse, Dashboard, Office } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

/** The backend being down is the most likely failure in a live demo, so it gets
 *  a message a person can act on rather than a stack trace. */
class ApiError extends Error {
  constructor(message: string, readonly hint?: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(
      "Cannot reach the Navigator service.",
      `Start it with: uvicorn backend.app.main:app --port 8000  (expected at ${BASE})`,
    );
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(
      `The service returned ${response.status}.`,
      detail.slice(0, 300) || undefined,
    );
  }

  return response.json() as Promise<T>;
}

export const ask = (question: string) =>
  request<AnswerResponse>("/ask", {
    method: "POST",
    body: JSON.stringify({ question }),
  });

export const analytics = () => request<Dashboard>("/analytics");

export const services = () =>
  request<{
    services: {
      id: string;
      name: string;
      category: string;
      documented: boolean;
      office: string | null;
    }[];
    offices: Office[];
  }>("/services");

export { ApiError };
