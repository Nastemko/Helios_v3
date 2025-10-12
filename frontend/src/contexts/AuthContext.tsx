import { createContext, useContext, useEffect, useState, ReactNode } from 'react';
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

  useEffect(() => {
    const initAuth = async () => {
      // Check for auth token in URL (after OAuth redirect)
      const params = new URLSearchParams(window.location.search);
      const token = params.get('token');
      
      if (token) {
        console.log('[Auth] Token received from OAuth redirect, length:', token.length);
        console.log('[Auth] Token preview:', token.substring(0, 30) + '...');
        localStorage.setItem('auth_token', token);
        // Remove token from URL
        window.history.replaceState({}, '', window.location.pathname);
        
        // Load user immediately after setting token
        try {
          console.log('[Auth] Calling /api/auth/me with new token...');
          const response = await authApi.me();
          console.log('[Auth] User loaded successfully:', response.data);
          setUser(response.data);
        } catch (error) {
          console.error('[Auth] Failed to load user after OAuth:', error);
          localStorage.removeItem('auth_token');
          setUser(null);
        } finally {
          setIsLoading(false);
        }
        return;
      }
      
      // Load user if token exists in localStorage
      const existingToken = localStorage.getItem('auth_token');
      if (existingToken) {
        console.log('[Auth] Found existing token in localStorage, length:', existingToken.length);
        try {
          const response = await authApi.me();
          console.log('[Auth] User loaded from existing token:', response.data);
          setUser(response.data);
        } catch (error) {
          // Token invalid or expired
          console.error('[Auth] Token validation failed:', error);
          localStorage.removeItem('auth_token');
          setUser(null);
        } finally {
          setIsLoading(false);
        }
      } else {
        console.log('[Auth] No token found, user not authenticated');
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

