/**
 * API client. Cookies carry the session; the CSRF token is echoed in a header on every write.
 * - 401: one silent refresh of the session, then the request is retried.
 * - 403 STEP_UP_REQUIRED: the password prompt opens, then the request is retried.
 * - Offline writes fail at once with OFFLINE, so the UI can say "saving needs a connection".
 */
import type { components } from "./schema";

export type Schemas = components["schemas"];

export class ApiError extends Error {
  constructor(
    public code: string,
    public status: number,
    public params: Record<string, string | number | boolean | null> = {},
    public fields: { field: string; code: string }[] = [],
  ) {
    super(code);
  }
}

type StepUpHandler = () => Promise<boolean>;
let stepUpHandler: StepUpHandler | null = null;
let onSignedOut: (() => void) | null = null;

export function setStepUpHandler(handler: StepUpHandler | null): void {
  stepUpHandler = handler;
}

export function setSignedOutHandler(handler: (() => void) | null): void {
  onSignedOut = handler;
}

function csrf(): string {
  const match = document.cookie.match(/(?:^|; )lt_csrf=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

type Query = Record<string, string | number | boolean | null | undefined>;

interface Options {
  body?: unknown;
  query?: Query;
  form?: FormData;
  raw?: boolean;
  retried?: boolean;
  steppedUp?: boolean;
  headers?: Record<string, string>;
}

function buildUrl(path: string, query?: Query): string {
  const url = new URL(`/api/v1${path}`, window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  return url.pathname + url.search;
}

let refreshing: Promise<boolean> | null = null;

async function refreshSession(): Promise<boolean> {
  refreshing ??= fetch("/api/v1/auth/refresh", {
    method: "POST",
    credentials: "same-origin",
    headers: { "X-CSRF-Token": csrf() },
  })
    .then((r) => r.ok)
    .catch(() => false)
    .finally(() => {
      setTimeout(() => (refreshing = null), 0);
    });
  return refreshing;
}

export async function request<T>(method: string, path: string, opts: Options = {}): Promise<T> {
  const write = method !== "GET";
  if (write && !navigator.onLine) throw new ApiError("OFFLINE", 0);
  const headers: Record<string, string> = { Accept: "application/json", ...opts.headers };
  if (write) headers["X-CSRF-Token"] = csrf();
  let body: BodyInit | undefined;
  if (opts.form) body = opts.form;
  else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }
  let res: Response;
  try {
    res = await fetch(buildUrl(path, opts.query), { method, headers, body, credentials: "same-origin" });
  } catch {
    throw new ApiError(navigator.onLine ? "NETWORK_ERROR" : "OFFLINE", 0);
  }
  if (res.status === 401 && !opts.retried && !path.startsWith("/auth/")) {
    if (await refreshSession()) return request<T>(method, path, { ...opts, retried: true });
    onSignedOut?.();
  }
  if (!res.ok) {
    let payload: { error?: { code?: string; params?: Record<string, string>; fields?: { field: string; code: string }[] } } = {};
    try {
      payload = await res.json();
    } catch {
      /* not JSON */
    }
    const code = payload.error?.code ?? `HTTP_${res.status}`;
    if (code === "STEP_UP_REQUIRED" && !opts.steppedUp && stepUpHandler) {
      if (await stepUpHandler()) return request<T>(method, path, { ...opts, steppedUp: true });
      throw new ApiError("STEP_UP_CANCELLED", 403);
    }
    throw new ApiError(code, res.status, payload.error?.params ?? {}, payload.error?.fields ?? []);
  }
  if (opts.raw) return res as unknown as T;
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string, query?: Query) => request<T>("GET", path, { query }),
  post: <T>(path: string, body?: unknown, query?: Query) => request<T>("POST", path, { body, query }),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, { body }),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, { body }),
  delete: <T>(path: string) => request<T>("DELETE", path),
  upload: <T>(path: string, form: FormData) => request<T>("POST", path, { form }),
};

/** Opens a PDF/CSV the server generates (needs the session cookie, so not a plain link). */
export async function openFile(path: string, query?: Query, download = false): Promise<void> {
  const res = await request<Response>("GET", path, { query, raw: true });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const disposition = res.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "file";
  if (download || !blob.type.includes("pdf")) {
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
  } else {
    window.open(url, "_blank", "noopener");
  }
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
}

/** Share a PDF through the phone's share sheet when available (receipts, statements). */
export async function shareFile(path: string, query?: Query): Promise<boolean> {
  const res = await request<Response>("GET", path, { query, raw: true });
  const blob = await res.blob();
  const name = /filename="([^"]+)"/.exec(res.headers.get("content-disposition") ?? "")?.[1] ?? "file.pdf";
  const file = new File([blob], name, { type: blob.type });
  if (navigator.canShare?.({ files: [file] })) {
    await navigator.share({ files: [file], title: name });
    return true;
  }
  const url = URL.createObjectURL(blob);
  window.open(url, "_blank", "noopener");
  return false;
}
