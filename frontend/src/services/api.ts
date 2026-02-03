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

// Text API
export const textApi = {
  list: (params?: {
    search?: string;
    language?: string;
    author?: string;
    skip?: number;
    limit?: number;
  }) => api.get<Text[]>("/api/texts", { params }),

  get: (urn: string, params?: { skip?: number; limit?: number }) =>
    api.get<TextDetail>(`/api/texts/${encodeURIComponent(urn)}`, { params }),

  getSegment: (urn: string, reference: string) =>
    api.get<TextSegment>(
      `/api/texts/${encodeURIComponent(urn)}/segment/${reference}`,
    ),

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
    text_id: number;
    segment_id: number;
    word: string;
    note: string;
  }) => api.post<Annotation>("/api/annotations", data),

  list: (params?: { text_id?: number; segment_id?: number; word?: string }) =>
    api.get<Annotation[]>("/api/annotations", { params }),

  get: (id: number) => api.get<Annotation>(`/api/annotations/${id}`),

  update: (id: number, note: string) =>
    api.put<Annotation>(`/api/annotations/${id}`, { note }),

  delete: (id: number) => api.delete(`/api/annotations/${id}`),

  getTextSummary: (text_id: number) =>
    api.get(`/api/annotations/text/${text_id}/summary`),
};



// Auth API
export const authApi = {
  loginGoogle: () => {
    window.location.href = `${API_BASE_URL}/api/auth/login/google`;
  },

  // Dev login for local testing without OAuth
  devLogin: () =>
    api.post<{ access_token: string; token_type: string; user: User }>(
      "/api/auth/dev-login",
    ),

  me: () => api.get<User>("/api/auth/me"),

  logout: () => {
    localStorage.removeItem("auth_token");
    return api.post("/api/auth/logout");
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
  }) => api.get<InscriptionListItem[]>("/api/inscriptions", { params }),

  // Get single inscription by PHI ID
  get: (phiId: number) => api.get<Inscription>(`/api/inscriptions/${phiId}`),

  // Get list of regions with counts
  getRegions: (level: "main" | "sub" = "main") =>
    api.get<RegionCount[]>("/api/inscriptions/regions", { params: { level } }),

  // Get corpus statistics
  getStats: () => api.get<InscriptionStats>("/api/inscriptions/stats"),

  // ML model endpoints - Ithaca for Greek, Aeneas for Latin
  restore: (
    text: string,
    language: "greek" | "latin" = "greek",
    temperature: number = 1.0
  ) =>
    api.post<RestorationResult>("/api/inscriptions/restore", {
      text,
      language,
      temperature,
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
