const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
const TOKEN_KEY = "nexusflow-access-token";

async function accessToken(): Promise<string> {
  const existing = sessionStorage.getItem(TOKEN_KEY);
  if (existing) return existing;
  const response = await fetch(`${API_BASE_URL}/auth/session`, { method: "POST" });
  if (!response.ok) throw new Error("Unable to establish a secure session.");
  const payload = await response.json() as { access_token: string };
  sessionStorage.setItem(TOKEN_KEY, payload.access_token);
  return payload.access_token;
}

export type ApiError = Error & { status?: number };

export async function apiRequest<T>(
  path: string,
  options: RequestInit = {},
): Promise<{ data: T; headers: Headers }> {
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 45_000);
  try {
    const token = path === "/auth/session" ? "" : await accessToken();
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(options.headers || {}),
      },
    });
    const payload = response.status === 204 ? null : await response.json().catch(() => ({}));
    if (!response.ok) {
      if (response.status === 401 && path !== "/auth/session") {
        sessionStorage.removeItem(TOKEN_KEY);
      }
      const error = new Error(
        payload?.detail || "NexusFlow could not complete that request.",
      ) as ApiError;
      error.status = response.status;
      throw error;
    }
    return { data: payload as T, headers: response.headers };
  } finally {
    window.clearTimeout(timeout);
  }
}

export async function getApi<T>(path: string): Promise<T> {
  const result = await apiRequest<T>(path);
  return result.data;
}

export async function postApi<T>(
  path: string,
  body: unknown,
): Promise<{ data: T; headers: Headers }> {
  return apiRequest<T>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function deleteApi(path: string): Promise<void> {
  await apiRequest<null>(path, { method: "DELETE" });
}
