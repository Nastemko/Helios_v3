import { useMutation } from '@tanstack/react-query';
import type { AxiosError } from 'axios';
import { translateAssistApi } from '../services/api';
import type { TranslationResult } from '../types';

export interface TranslatePayload {
  text: string;
  language?: string;
}

export function useTranslationAssist() {
  return useMutation<TranslationResult, AxiosError, TranslatePayload>({
    mutationFn: async (payload) => {
      const response = await translateAssistApi.translate(payload);
      return response.data;
    },
  });
}

