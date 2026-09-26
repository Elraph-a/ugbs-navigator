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
    if (response.status === 401) {
      throw new ApiError("Wrong password.", "Check it and try again.");
    }
    if (response.status === 503) {
      throw new ApiError(
        "The dashboard is not configured.",
        "Set ADMIN_PASSWORD on the server, then reload.",
      );
    }
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

/** The dashboard password, kept for this browser session only: closing the tab
 *  signs you out, and it never reaches localStorage or a cookie. */
const KEY = "ugbs-admin-key";

export const adminKey = () => {
  try {
    return sessionStorage.getItem(KEY) ?? "";
  } catch {
    return "";
  }
};

export const rememberAdminKey = (key: string) => {
  try {
    sessionStorage.setItem(KEY, key);
  } catch {
    /* private browsing: the password simply has to be typed again */
  }
};

export const forgetAdminKey = () => {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* nothing stored, nothing to clear */
  }
};

export const analytics = (key = adminKey()) =>
  request<Dashboard>("/analytics", { headers: { "X-Admin-Key": key } });

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
