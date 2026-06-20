/**
 * Thin fetch wrapper for the WABAG RFQ backend.
 *
 * - Base URL comes from VITE_API_BASE_URL (see .env.example), defaulting to the
 *   local dev backend.
 * - Multipart uploads pass FormData straight through — fetch sets the
 *   multipart boundary; never set Content-Type manually for FormData.
 * - Errors are thrown as ApiError so callers can switch on status (404, 415,
 *   422, 503, etc.) and read the backend's `detail` string.
 */

const DEFAULT_BASE_URL = "http://127.0.0.1:8000/api/v1";

export class ApiError extends Error {
  readonly status: number;
  /** Parsed body if the response was JSON, else null. */
  readonly body: unknown;
  /** Raw response detail string (FastAPI error detail) when available. */
  readonly detail: string | undefined;

  constructor(status: number, message: string, body: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
    if (body && typeof body === "object" && "detail" in body) {
      const d = (body as { detail?: unknown }).detail;
      this.detail =
        typeof d === "string" ? d : (JSON.stringify(d) ?? undefined);
    }
  }
}

function baseUrl(): string {
  return (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_BASE_URL).replace(
    /\/$/,
    "",
  );
}

function joinUrl(path: string): string {
  const base = baseUrl();
  const clean = path.startsWith("/") ? path : `/${path}`;
  return `${base}${clean}`;
}

function buildHeaders(init?: RequestInit): HeadersInit {
  // Copy caller-provided headers but never let Content-Type leak into a
  // FormData request (fetch must set the boundary itself).
  const headers = new Headers(init?.headers);
  if (headers.has("Content-Type")) {
    if (init?.body instanceof FormData) {
      headers.delete("Content-Type");
    }
  }
  return headers;
}

async function parseBody(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function detailMessage(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail?: unknown }).detail;
    if (typeof d === "string") return d;
    if (d != null) return JSON.stringify(d);
  }
  return "Request failed";
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: BodyInit | object | null;
  /** Treat 404 as a thrown ApiError (default) or as a `null` result. */
  nullOnNotFound?: boolean;
}

async function request<T>(
  path: string,
  { body, nullOnNotFound = false, ...init }: RequestOptions = {},
): Promise<T> {
  const method = init.method ?? (body != null ? "POST" : "GET");

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body != null) {
    payload = JSON.stringify(body);
  }

  const headers = buildHeaders({
    ...init,
    headers: init.headers,
  });
  if (payload && !(body instanceof FormData)) {
    (headers as Headers).set("Content-Type", "application/json");
  }

  const response = await fetch(joinUrl(path), {
    ...init,
    method,
    headers,
    body: payload,
  });

  if (response.status === 404 && nullOnNotFound) {
    return null as T;
  }

  if (!response.ok) {
    const errBody = await parseBody(response);
    throw new ApiError(response.status, detailMessage(errBody), errBody);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await parseBody(response)) as T;
}

export const apiClient = {
  get: <T>(path: string, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "GET" }),
  post: <T>(
    path: string,
    body?: BodyInit | object | null,
    opts?: RequestOptions,
  ) => request<T>(path, { ...opts, method: "POST", body }),
  patch: <T>(
    path: string,
    body?: BodyInit | object | null,
    opts?: RequestOptions,
  ) => request<T>(path, { ...opts, method: "PATCH", body }),
  delete: <T>(path: string, opts?: RequestOptions) =>
    request<T>(path, { ...opts, method: "DELETE" }),
};
