import type { AxiosError } from "axios";
import { useMutation } from "@tanstack/react-query";

import { tutorApi } from "../services/api";
import type { TranslationSuggestion } from "../types";

export interface TranslationSuggestionPayload {
  text_id: number;
  segment_id: number;
  selection: string;
  translation_draft?: string;
  language?: string;
  metadata?: Record<string, unknown>;
}

export function useTranslationSuggestion() {
  return useMutation<TranslationSuggestion, AxiosError, TranslationSuggestionPayload>({
    mutationFn: async (payload) => {
      const response = await tutorApi.suggestTranslation(payload);
      return response.data;
    },
  });
}


