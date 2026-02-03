// Type definitions for Helios frontend

export interface User {
  id: number;
  email: string;
  oauth_provider?: string;
  created_at?: string;
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





// Translation Assist types
export interface TranslationResult {
  source_text: string;
  translation: string;
  literal_gloss?: string | null;
  rationale: string;
  confidence: number;
  language: string;
}

export interface TranslationCard {
  id: string;
  source_text: string;
  translation: string;
  literal_gloss?: string | null;
  rationale: string;
  confidence: number;
  language: string;
  created_at: string;
}

export interface TranslateAssistStatus {
  enabled: boolean;
  model: string | null;
  max_chars: number;
}

// ============================================================================
// INSCRIPTION TYPES (PHI Corpus)
// ============================================================================

export interface Inscription {
  id: number;
  phi_id: number;
  urn: string;
  title: string;
  text: string;
  region_main: string | null;
  region_sub: string | null;
  date_str: string | null;
  date_min: number | null;
  date_max: number | null;
  date_circa: boolean | null;
  metadata_raw: string | null;
}

export interface InscriptionListItem {
  id: number;
  phi_id: number;
  urn: string;
  title: string;
  text_preview: string;
  region_main: string | null;
  region_sub: string | null;
  date_str: string | null;
  date_min: number | null;
  date_max: number | null;
}

export interface RegionCount {
  region: string;
  region_id: string | null;
  count: number;
}

export interface InscriptionStats {
  total_inscriptions: number;
  inscriptions_with_dates: number;
  regions_count: number;
  date_range: {
    earliest: number | null;
    latest: number | null;
  };
}

// Ithaca Model Result Types

export interface LocationPrediction {
  location_id: number;
  name: string;
  score: number;
}

export interface RestorationAlternative {
  text: string;
  score: number;
}

export interface RestorationResult {
  input_text: string;
  top_prediction: string;
  restored_indices: number[];
  alternatives: RestorationAlternative[];
  available: boolean;
  message: string;
}

export interface AttributionResult {
  input_text: string;
  locations: LocationPrediction[];
  year_scores: number[]; // 160 values for years -800 to +800
  predicted_date_range: {
    min: number | null;
    max: number | null;
    confidence: number;
  };
  available: boolean;
  message: string;
}

export interface SimilarInscription {
  phi_id: number;
  text: string;
  region: string | null;
  date_min: number | null;
  date_max: number | null;
  score: number;
}

export interface ContextualizationResult {
  similar: SimilarInscription[];
  available: boolean;
  message: string;
}

export interface ModelStatus {
  available: boolean;
  model_name: string;
}

export interface IthacaModelStatus {
  models: {
    greek: ModelStatus;
    latin: ModelStatus;
  };
  features: string[];
  supported_languages: string[];
}

