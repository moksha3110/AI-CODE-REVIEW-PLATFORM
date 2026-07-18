import {
  AUTH_SERVICE_URL,
  NOTIFICATION_SERVICE_URL,
  REPOSITORY_SERVICE_URL,
  REVIEW_SERVICE_URL,
} from "./config";
import type {
  ApiErrorBody,
  InstallUrlOut,
  Notification,
  PaginatedNotifications,
  PaginatedReviews,
  QualityTrendPoint,
  Repository,
  ReviewDetail,
} from "./types";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

interface FetchOptions extends RequestInit {
  accessToken?: string | null;
}

async function apiFetch<T>(url: string, options: FetchOptions = {}): Promise<T> {
  const { accessToken, headers, ...rest } = options;

  const response = await fetch(url, {
    ...rest,
    headers: {
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...headers,
    },
  });

  if (!response.ok) {
    let body: ApiErrorBody | null = null;
    try {
      body = (await response.json()) as ApiErrorBody;
    } catch {
      // Non-JSON error body (e.g. a raw 502 from an unrelated proxy) - fall
      // through and surface the HTTP status text instead.
    }
    throw new ApiError(response.status, body?.error.message ?? response.statusText, body?.error.code);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/**
 * Every protected call goes through here. On a 401 (expired access token -
 * they only live 15 minutes) it asks the caller-supplied `refresh` callback
 * for a new one and retries exactly once. `refresh` is AuthContext's
 * `refreshAccessToken`, which itself de-dupes concurrent callers, so it's
 * safe for several components to 401 around the same moment.
 */
async function authorizedFetch<T>(
  url: string,
  accessToken: string | null,
  refresh: () => Promise<string | null>,
  options: RequestInit = {},
): Promise<T> {
  try {
    return await apiFetch<T>(url, { ...options, accessToken });
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      const newToken = await refresh();
      if (!newToken) throw err;
      return await apiFetch<T>(url, { ...options, accessToken: newToken });
    }
    throw err;
  }
}

type Refresh = () => Promise<string | null>;

export const authApi = {
  me: (accessToken: string) =>
    apiFetch<import("./types").User>(`${AUTH_SERVICE_URL}/api/v1/auth/me`, { accessToken }),
  refresh: () =>
    apiFetch<{ access_token: string; expires_in: number }>(`${AUTH_SERVICE_URL}/api/v1/auth/refresh`, {
      method: "POST",
      credentials: "include",
    }),
  logout: () =>
    apiFetch<{ status: string }>(`${AUTH_SERVICE_URL}/api/v1/auth/logout`, {
      method: "POST",
      credentials: "include",
    }),
  loginUrl: () => `${AUTH_SERVICE_URL}/api/v1/auth/github/login`,
};

export const repositoryApi = {
  list: (accessToken: string | null, refresh: Refresh) =>
    authorizedFetch<Repository[]>(`${REPOSITORY_SERVICE_URL}/api/v1/repositories`, accessToken, refresh),
  getInstallUrl: (accessToken: string | null, refresh: Refresh) =>
    authorizedFetch<InstallUrlOut>(
      `${REPOSITORY_SERVICE_URL}/api/v1/repositories/install`,
      accessToken,
      refresh,
    ),
};

export const reviewApi = {
  list: (
    repositoryId: string,
    params: { limit?: number; offset?: number },
    accessToken: string | null,
    refresh: Refresh,
  ) => {
    const query = new URLSearchParams();
    if (params.limit) query.set("limit", String(params.limit));
    if (params.offset) query.set("offset", String(params.offset));
    const qs = query.toString() ? `?${query.toString()}` : "";
    return authorizedFetch<PaginatedReviews>(
      `${REVIEW_SERVICE_URL}/api/v1/repositories/${repositoryId}/reviews${qs}`,
      accessToken,
      refresh,
    );
  },
  get: (reviewId: string, accessToken: string | null, refresh: Refresh) =>
    authorizedFetch<ReviewDetail>(`${REVIEW_SERVICE_URL}/api/v1/reviews/${reviewId}`, accessToken, refresh),
  qualityTrends: (repositoryId: string, accessToken: string | null, refresh: Refresh) =>
    authorizedFetch<QualityTrendPoint[]>(
      `${REVIEW_SERVICE_URL}/api/v1/repositories/${repositoryId}/quality-trends`,
      accessToken,
      refresh,
    ),
};

export const notificationApi = {
  list: (
    params: { unreadOnly?: boolean; limit?: number; offset?: number },
    accessToken: string | null,
    refresh: Refresh,
  ) => {
    const query = new URLSearchParams();
    if (params.unreadOnly) query.set("unread_only", "true");
    if (params.limit) query.set("limit", String(params.limit));
    if (params.offset) query.set("offset", String(params.offset));
    const qs = query.toString() ? `?${query.toString()}` : "";
    return authorizedFetch<PaginatedNotifications>(
      `${NOTIFICATION_SERVICE_URL}/api/v1/notifications${qs}`,
      accessToken,
      refresh,
    );
  },
  markRead: (notificationId: string, accessToken: string | null, refresh: Refresh) =>
    authorizedFetch<Notification>(
      `${NOTIFICATION_SERVICE_URL}/api/v1/notifications/${notificationId}/read`,
      accessToken,
      refresh,
      { method: "POST" },
    ),
};
