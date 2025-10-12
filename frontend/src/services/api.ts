import axios from 'axios';
import type { Text, TextDetail, TextSegment, WordAnalysis, Annotation, User, AeneasStatus } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_URL || '';

// Create axios instance
const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token to requests
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Text API
export const textApi = {
  list: (params?: { search?: string; language?: string; author?: string; skip?: number; limit?: number }) =>
    api.get<Text[]>('/api/texts', { params }),
  
  get: (urn: string, params?: { skip?: number; limit?: number }) =>
    api.get<TextDetail>(`/api/texts/${encodeURIComponent(urn)}`, { params }),
  
  getSegment: (urn: string, reference: string) =>
    api.get<TextSegment>(`/api/texts/${encodeURIComponent(urn)}/segment/${reference}`),
  
  getAuthors: () =>
    api.get<Array<{ author: string; work_count: number }>>('/api/texts/authors/list'),
  
  getStats: () =>
    api.get('/api/texts/stats/summary'),
};

// Analysis API
export const analysisApi = {
  analyzeWord: (word: string, language: string, context?: string) =>
    api.post<WordAnalysis>('/api/analyze/word', { word, language, context }),
};

// Aeneas AI API
export const aeneasApi = {
  status: () =>
    api.get<AeneasStatus>('/api/aeneas/status'),
  
  restore: (text: string, language: string, options?: { beam_width?: number; temperature?: number; max_len?: number }) =>
    api.post('/api/aeneas/restore', { text, language, ...options }),
  
  attribute: (text: string, language: string) =>
    api.post('/api/aeneas/attribute', { text, language }),
  
  contextualize: (text: string, language: string) =>
    api.post('/api/aeneas/contextualize', { text, language }),
};

// Annotation API
export const annotationApi = {
  create: (data: { text_id: number; segment_id: number; word: string; note: string }) =>
    api.post<Annotation>('/api/annotations', data),
  
  list: (params?: { text_id?: number; segment_id?: number; word?: string }) =>
    api.get<Annotation[]>('/api/annotations', { params }),
  
  get: (id: number) =>
    api.get<Annotation>(`/api/annotations/${id}`),
  
  update: (id: number, note: string) =>
    api.put<Annotation>(`/api/annotations/${id}`, { note }),
  
  delete: (id: number) =>
    api.delete(`/api/annotations/${id}`),
  
  getTextSummary: (text_id: number) =>
    api.get(`/api/annotations/text/${text_id}/summary`),
};

// Auth API
export const authApi = {
  loginGoogle: () => {
    // Use full URL for OAuth redirect (can't use proxy for full page redirect)
    window.location.href = `http://localhost:8000/api/auth/login/google`;
  },
  
  me: () =>
    api.get<User>('/api/auth/me'),
  
  logout: () => {
    localStorage.removeItem('auth_token');
    return api.post('/api/auth/logout');
  },
  
  status: () =>
    api.get<{ authenticated: boolean; user: User | null }>('/api/auth/status'),
};

export default api;

