"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { authApi } from "./api-client";
import type { User } from "./types";

interface AuthContextValue {
  user: User | null;
  accessToken: string | null;
  /** True until the initial silent-refresh attempt (on app load) resolves. */
  isLoading: boolean;
  login: () => void;
  logout: () => Promise<void>;
  /**
   * Exchanges the httpOnly refresh cookie for a new access token. De-duped:
   * concurrent callers (e.g. two components 401ing around the same moment)
   * share one in-flight request instead of racing separate refresh-token
   * rotations against each other.
   */
  refreshAccessToken: () => Promise<string | null>;
  /** Called once by the OAuth callback page with the token from the URL fragment. */
  setAccessTokenFromCallback: (token: string) => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [accessToken, setAccessToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const refreshInFlight = useRef<Promise<string | null> | null>(null);

  // Set synchronously (via ref, not state) by setAccessTokenFromCallback.
  // React fires child effects before parent effects within the same commit,
  // so when /auth/callback is the page that's mounting the whole app (the
  // real-world case - GitHub's redirect lands the browser there fresh),
  // its effect runs *before* this provider's own mount effect below. A
  // generation-counter guard alone doesn't help here: by the time the mount
  // effect captures its baseline, the callback has already bumped it, so a
  // late-resolving silent-refresh failure would still look "current" and
  // wipe out the token the callback just set. Checking this flag lets the
  // mount effect skip its silent refresh entirely when that's happened,
  // instead of trying to race it.
  const callbackTokenApplied = useRef(false);

  const loadUser = useCallback(async (token: string) => {
    try {
      setUser(await authApi.me(token));
    } catch {
      setUser(null);
    }
  }, []);

  const refreshAccessToken = useCallback((): Promise<string | null> => {
    if (refreshInFlight.current) {
      return refreshInFlight.current;
    }
    const promise = (async () => {
      try {
        const data = await authApi.refresh();
        setAccessToken(data.access_token);
        return data.access_token;
      } catch {
        setAccessToken(null);
        setUser(null);
        return null;
      } finally {
        refreshInFlight.current = null;
      }
    })();
    refreshInFlight.current = promise;
    return promise;
  }, []);

  // Silent session restore on load: a page refresh loses the in-memory
  // access token (by design - it's never persisted to localStorage), but
  // the httpOnly refresh cookie survives, so this exchanges it for a fresh
  // access token instead of forcing the user back through GitHub login.
  // Skipped entirely if the OAuth callback already established a session
  // on this same mount (see callbackTokenApplied above).
  useEffect(() => {
    if (callbackTokenApplied.current) {
      setIsLoading(false);
      return;
    }
    (async () => {
      const token = await refreshAccessToken();
      if (token) await loadUser(token);
      setIsLoading(false);
    })();
  }, [refreshAccessToken, loadUser]);

  const setAccessTokenFromCallback = useCallback(
    (token: string) => {
      callbackTokenApplied.current = true;
      setAccessToken(token);
      void loadUser(token);
    },
    [loadUser],
  );

  const login = useCallback(() => {
    window.location.href = authApi.loginUrl();
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      setAccessToken(null);
      setUser(null);
    }
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, accessToken, isLoading, login, logout, refreshAccessToken, setAccessTokenFromCallback }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return ctx;
}
