// Type definitions for Helios frontend

export interface User {
  id: number;
  email: string;
  oauth_provider: string;
}

export interface Text {
  id: number;
  urn: string;
  author: string;
  title: string;
  language: string;
  is_fragment: boolean;
  text_metadata?: Record<string, any>;
}

export interface TextSegment {
  id: number;
  book: string;
  line: string;
  content: string;
  reference: string;
  sequence: number;
}

export interface TextDetail {
  text: Text;
  segments: TextSegment[];
  total_segments: number;
}

export interface WordAnalysis {
  word: string;
  language: string;
  lemma: string;
  pos: string;
  morphology: Record<string, string>;
  definitions: string[];
}

export interface Annotation {
  id: number;
  user_id: number;
  text_id: number;
  segment_id: number;
  word: string;
  note: string;
  created_at: string;
  updated_at?: string;
}

export interface StudentNote {
  id: number;
  user_id: number;
  text_id?: number;
  content: string;
  created_at: string;
  updated_at?: string;
}

export interface Highlight {
  id: number;
  user_id: number;
  text_id: number;
  segment_id: number;
  start_offset: number;
  end_offset: number;
  selected_text: string;
  color: string;
  created_at: string;
}

export interface AeneasStatus {
  available: boolean;
  models: {
    greek: boolean;
    latin: boolean;
  };
  message: string;
}

