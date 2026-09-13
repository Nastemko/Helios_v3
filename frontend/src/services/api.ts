import axios from "axios";
import type {
  Text,
  TextDetail,
  TextSegment,
  WordAnalysis,
  Annotation,
  User,
  TranslationResult,
  TranslateAssistStatus,

  Inscription,
  InscriptionListItem,
  RegionCount,
  InscriptionStats,
  RestorationResult,
  AttributionResult,
  ContextualizationResult,
  IthacaModelStatus,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";
const API_PREFIX = import.meta.env.VITE_API_PREFIX || "/api";
const API_TIMEOUT_MS = Number(import.meta.env.VITE_API_TIMEOUT_MS || 30000);
export const LOGIN_PATH = import.meta.env.VITE_LOGIN_PATH || "/login";
export const AUTH_TOKEN_KEY = import.meta.env.VITE_AUTH_TOKEN_KEY || "auth_token";

// Validated at the boundary: any value other than "latin" falls back to Greek
// rather than sending an invalid language to the backend.
const _defaultLang: unknown = import.meta.env.VITE_DEFAULT_LANG;
const DEFAULT_LANG: "greek" | "latin" =
  _defaultLang === "latin" ? "latin" : "greek";

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT_MS,
  headers: {
    "Content-Type": "application/json",
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// A 401 means the token expired or was revoked. Without this, an expired
// session is only ever noticed on a cold page load, so the app keeps
// rendering as authenticated while every request fails.
// Auth endpoints are exempt: AuthContext handles their failures itself, and
// redirecting on them would break the login flow.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const isAuthEndpoint = error.config?.url?.startsWith(`${API_PREFIX}/auth/`);
    if (error.response?.status === 401 && !isAuthEndpoint) {
      localStorage.removeItem(AUTH_TOKEN_KEY);
      if (window.location.pathname !== LOGIN_PATH) {
        window.location.href = LOGIN_PATH;
      }
    }
    return Promise.reject(error);
  },
);

  // Text API
export const textApi = {
  list: (params?: {
    search?: string;
    language?: string;
    author?: string;
    skip?: number;
    limit?: number;
  }) => api.get<Text[]>(`${API_PREFIX}/texts/`, { params }),

  // No trailing slash below: these routes are declared without one, and the
  // 307 redirect FastAPI issues to correct the path drops the Authorization
  // header in some clients on cross-origin requests.
  get: (textId: number, params?: { skip?: number; limit?: number }) =>
    api.get<TextDetail>(`${API_PREFIX}/texts/${textId}`, { params }),

  getSegment: (textId: number, reference: string) =>
    api.get<TextSegment>(`${API_PREFIX}/texts/${textId}/segment/${reference}`),

  getAuthors: () =>
    api.get<Array<{ author: string; work_count: number }>>(
      `${API_PREFIX}/texts/authors/list`,
    ),

  getStats: () => api.get(`${API_PREFIX}/texts/stats/summary`),
};

// Analysis API
export const analysisApi = {
  analyzeWord: (word: string, language: string, context?: string) =>
    api.post<WordAnalysis>(`${API_PREFIX}/analyze/word`, { word, language, context }),
};



// Annotation API
export const annotationApi = {
  create: (data: {
    lang_version_id: number;
    segment_id: number;
    word: string;
    note: string;
  }) => api.post<Annotation>(`${API_PREFIX}/annotations/`, data),

  list: (params?: {
    lang_version_id?: number;
    segment_id?: number;
    word?: string;
  }) => api.get<Annotation[]>(`${API_PREFIX}/annotations/`, { params }),

  get: (id: number) => api.get<Annotation>(`${API_PREFIX}/annotations/${id}`),

  update: (id: number, note: string) =>
    api.put<Annotation>(`${API_PREFIX}/annotations/${id}`, { note }),

  delete: (id: number) => api.delete(`${API_PREFIX}/annotations/${id}`),

  getVersionSummary: (lang_version_id: number) =>
    api.get(`${API_PREFIX}/annotations/version/${lang_version_id}/summary`),
};



// Auth API
export const authApi = {
  loginGoogle: () => {
    window.location.href = `${API_BASE_URL}${API_PREFIX}/auth/login/google`;
  },

  me: () => api.get<User>(`${API_PREFIX}/auth/me`),

  // The POST goes out before the token is cleared so the request is still
  // authenticated and the server can identify the caller.
  logout: async () => {
    try {
      return await api.post(`${API_PREFIX}/auth/logout`);
    } finally {
      localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  },

  status: () =>
    api.get<{ authenticated: boolean; user: User | null }>(`${API_PREFIX}/auth/status`),
};

// Translation Assist API
export const translateAssistApi = {
  translate: (data: { text: string; language?: string }) =>
    api.post<TranslationResult>(`${API_PREFIX}/translate-assist`, data),

  status: () => api.get<TranslateAssistStatus>(`${API_PREFIX}/translate-assist/status`),
};

// Inscription API (PHI Corpus)
export const inscriptionApi = {
  // List inscriptions with filtering
  list: (params?: {
    search?: string;
    region_main?: string;
    region_sub?: string;
    date_min?: number;
    date_max?: number;
    skip?: number;
    limit?: number;
  }) => api.get<InscriptionListItem[]>(`${API_PREFIX}/inscriptions/`, { params }),

  // Get single inscription by text ID
  get: (textId: number) => api.get<Inscription>(`${API_PREFIX}/inscriptions/${textId}`),

  // Get list of regions with counts
  getRegions: (level: "main" | "sub" = "main") =>
    api.get<RegionCount[]>(`${API_PREFIX}/inscriptions/regions`, { params: { level } }),

  // Get corpus statistics
  getStats: () => api.get<InscriptionStats>(`${API_PREFIX}/inscriptions/stats`),

  // ML model endpoints - Ithaca for Greek, Aeneas for Latin
  restore: (
    text: string,
    language: "greek" | "latin" = DEFAULT_LANG,
    temperature: number = Number(import.meta.env.VITE_RESTORE_TEMP || 1.0),
    // Longest gap a '#' may expand to. Omit to use the server default (15).
    // Only affects texts containing '#'; cost is roughly linear in it.
    maxRestorationLen?: number
  ) =>
    api.post<RestorationResult>(`${API_PREFIX}/inscriptions/restore`, {
      text,
      language,
      temperature,
      ...(maxRestorationLen !== undefined && {
        max_restoration_len: maxRestorationLen,
      }),
    }),

  attribute: (text: string, language: "greek" | "latin" = DEFAULT_LANG) =>
    api.post<AttributionResult>(`${API_PREFIX}/inscriptions/attribute`, {
      text,
      language,
    }),

  contextualize: (
    text: string,
    language: "greek" | "latin" = DEFAULT_LANG,
    topK: number = Number(import.meta.env.VITE_CONTEXT_TOP_K || 20)
  ) =>
    api.post<ContextualizationResult>(`${API_PREFIX}/inscriptions/contextualize`, {
      text,
      language,
      top_k: topK,
    }),

  // Check model status
  getModelStatus: () =>
    api.get<IthacaModelStatus>(`${API_PREFIX}/inscriptions/model/status`),
};

export default api;
