import { useMemo, useState } from "react";
import type { TranslationSuggestion } from "../../types";

interface HighlightPopoverProps {
  selection: string;
  reference: string;
  position: { top: number; left: number };
  containerWidth: number;
  onAskTutor: () => void;
  onClose: () => void;
  isLoading: boolean;
  suggestion?: TranslationSuggestion | null;
  errorMessage?: string | null;
}

const POPOVER_WIDTH = 320;

export default function HighlightPopover({
  selection,
  reference,
  position,
  containerWidth,
  onAskTutor,
  onClose,
  isLoading,
  suggestion,
  errorMessage,
}: HighlightPopoverProps) {
  const [copied, setCopied] = useState(false);

  const left = useMemo(() => {
    const clampMax = Math.max(containerWidth - POPOVER_WIDTH, 0);
    const centered = position.left - POPOVER_WIDTH / 2;
    if (centered < 0) {
      return 0;
    }
    if (centered > clampMax) {
      return clampMax;
    }
    return centered;
  }, [position.left, containerWidth]);

  const handleCopy = async () => {
    if (!suggestion?.translation) return;
    try {
      await navigator.clipboard.writeText(suggestion.translation);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      console.warn("Clipboard unavailable", err);
    }
  };

  return (
    <div
      className="absolute z-30 w-80"
      style={{ top: position.top, left, width: POPOVER_WIDTH }}
    >
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-xl space-y-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <p className="text-xs uppercase tracking-wide text-slate-500">
              Selected ({reference})
            </p>
            <p className="mt-1 text-base font-medium greek-text">{selection}</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 transition"
            aria-label="Dismiss highlight"
          >
            &times;
          </button>
        </div>

        {suggestion ? (
          <div className="space-y-2">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold text-slate-600">Tutor Suggestion</p>
              <button
                onClick={handleCopy}
                className="text-xs text-blue-600 hover:text-blue-700"
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>
            <p className="text-base font-medium">{suggestion.translation}</p>
            {suggestion.literal_gloss && (
              <p className="text-sm text-slate-600">
                <span className="font-semibold">Literal: </span>
                {suggestion.literal_gloss}
              </p>
            )}
            <p className="text-sm text-slate-700 leading-relaxed">
              {suggestion.rationale}
            </p>
            <p className="text-xs text-slate-500">
              Confidence: {(suggestion.confidence * 100).toFixed(0)}%
            </p>
          </div>
        ) : (
          <div className="space-y-2 text-sm text-slate-600">
            <p>
              Ask the Helios tutor for a contextual translation suggestion of the
              highlighted passage.
            </p>
            {errorMessage && (
              <p className="rounded-md bg-red-50 p-2 text-xs text-red-700">
                {errorMessage}
              </p>
            )}
            <button
              onClick={onAskTutor}
              disabled={isLoading}
              className="w-full rounded-lg bg-blue-600 py-2 text-white font-semibold hover:bg-blue-700 disabled:cursor-not-allowed disabled:bg-blue-300 transition"
            >
              {isLoading ? "Contacting Tutor..." : "Ask Tutor"}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}


