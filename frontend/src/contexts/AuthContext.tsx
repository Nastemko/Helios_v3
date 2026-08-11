import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { authApi } from '../services/api';
import type { User } from '../types';

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: () => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const queryClient = useQueryClient();

  useEffect(() => {
    const initAuth = async () => {
      // Check for auth token in URL fragment (after OAuth redirect)
      // Using fragment (#token=...) instead of query param to prevent leakage via Referer headers
      const hash = window.location.hash;
      const tokenMatch = hash.match(/#token=(.+)/);
      const token = tokenMatch ? tokenMatch[1] : null;

      if (token) {
        localStorage.setItem('auth_token', token);
        // Remove token from URL
        window.history.replaceState({}, '', window.location.pathname);
      }

      // Load user if a token is now present (from the redirect or from a
      // previous session)
      if (localStorage.getItem('auth_token')) {
        try {
          const response = await authApi.me();
          setUser(response.data);
          setIsLoading(false);
          return;
        } catch (error) {
          // Token invalid or expired. Discard it and fall through to the
          // status check below rather than dead-ending on the login page:
          // if the backend has auth disabled, a stale token must not lock
          // the user out.
          console.error('[Auth] Token validation failed:', error);
          localStorage.removeItem('auth_token');
        }
      }

      // No usable token. Ask the backend whether authentication is required at
      // all: when it runs with DEBUG=True auth is disabled and it reports the
      // shared dev user, so we sign in without a token. The backend is the
      // single source of truth for which mode we are in.
      try {
        const response = await authApi.status();
        setUser(response.data.authenticated ? response.data.user : null);
      } catch (error) {
        console.error('[Auth] Failed to determine auth status:', error);
        setUser(null);
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();
  }, []);

  const login = () => {
    authApi.loginGoogle();
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } finally {
      setUser(null);
      // Drop cached server state so the previous session's texts and
      // annotations do not leak into the next login in this tab.
      queryClient.clear();
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

