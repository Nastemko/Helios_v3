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

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("auth_token");
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
    const isAuthEndpoint = error.config?.url?.startsWith("/api/auth/");
    if (error.response?.status === 401 && !isAuthEndpoint) {
      localStorage.removeItem("auth_token");
      if (window.location.pathname !== "/login") {
        window.location.href = "/login";
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
  }) => api.get<Text[]>("/api/texts/", { params }),

  // No trailing slash below: these routes are declared without one, and the
  // 307 redirect FastAPI issues to correct the path drops the Authorization
  // header in some clients on cross-origin requests.
  get: (textId: number, params?: { skip?: number; limit?: number }) =>
    api.get<TextDetail>(`/api/texts/${textId}`, { params }),

  getSegment: (textId: number, reference: string) =>
    api.get<TextSegment>(`/api/texts/${textId}/segment/${reference}`),

  getAuthors: () =>
    api.get<Array<{ author: string; work_count: number }>>(
      "/api/texts/authors/list",
    ),

  getStats: () => api.get("/api/texts/stats/summary"),
};

// Analysis API
export const analysisApi = {
  analyzeWord: (word: string, language: string, context?: string) =>
    api.post<WordAnalysis>("/api/analyze/word", { word, language, context }),
};



// Annotation API
export const annotationApi = {
  create: (data: {
    lang_version_id: number;
    segment_id: number;
    word: string;
    note: string;
  }) => api.post<Annotation>("/api/annotations/", data),

  list: (params?: {
    lang_version_id?: number;
    segment_id?: number;
    word?: string;
  }) => api.get<Annotation[]>("/api/annotations/", { params }),

  get: (id: number) => api.get<Annotation>(`/api/annotations/${id}`),

  update: (id: number, note: string) =>
    api.put<Annotation>(`/api/annotations/${id}`, { note }),

  delete: (id: number) => api.delete(`/api/annotations/${id}`),

  getVersionSummary: (lang_version_id: number) =>
    api.get(`/api/annotations/version/${lang_version_id}/summary`),
};



// Auth API
export const authApi = {
  loginGoogle: () => {
    window.location.href = `${API_BASE_URL}/api/auth/login/google`;
  },

  me: () => api.get<User>("/api/auth/me"),

  // The POST goes out before the token is cleared so the request is still
  // authenticated and the server can identify the caller.
  logout: async () => {
    try {
      return await api.post("/api/auth/logout");
    } finally {
      localStorage.removeItem("auth_token");
    }
  },

  status: () =>
    api.get<{ authenticated: boolean; user: User | null }>("/api/auth/status"),
};

// Translation Assist API
export const translateAssistApi = {
  translate: (data: { text: string; language?: string }) =>
    api.post<TranslationResult>("/api/translate-assist", data),

  status: () => api.get<TranslateAssistStatus>("/api/translate-assist/status"),
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
  }) => api.get<InscriptionListItem[]>("/api/inscriptions/", { params }),

  // Get single inscription by text ID
  get: (textId: number) => api.get<Inscription>(`/api/inscriptions/${textId}`),

  // Get list of regions with counts
  getRegions: (level: "main" | "sub" = "main") =>
    api.get<RegionCount[]>("/api/inscriptions/regions", { params: { level } }),

  // Get corpus statistics
  getStats: () => api.get<InscriptionStats>("/api/inscriptions/stats"),

  // ML model endpoints - Ithaca for Greek, Aeneas for Latin
  restore: (
    text: string,
    language: "greek" | "latin" = "greek",
    temperature: number = 1.0,
    // Longest gap a '#' may expand to. Omit to use the server default (15).
    // Only affects texts containing '#'; cost is roughly linear in it.
    maxRestorationLen?: number
  ) =>
    api.post<RestorationResult>("/api/inscriptions/restore", {
      text,
      language,
      temperature,
      ...(maxRestorationLen !== undefined && {
        max_restoration_len: maxRestorationLen,
      }),
    }),

  attribute: (text: string, language: "greek" | "latin" = "greek") =>
    api.post<AttributionResult>("/api/inscriptions/attribute", {
      text,
      language,
    }),

  contextualize: (
    text: string,
    language: "greek" | "latin" = "greek",
    topK: number = 20
  ) =>
    api.post<ContextualizationResult>("/api/inscriptions/contextualize", {
      text,
      language,
      top_k: topK,
    }),

  // Check model status
  getModelStatus: () =>
    api.get<IthacaModelStatus>("/api/inscriptions/model/status"),
};

export default api;
