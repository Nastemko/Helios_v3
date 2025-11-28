import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { textApi } from '../services/api';
import WordAnalysisPanel from '../components/WordAnalysisPanel';
import HighlightPopover from '../components/highlighting/HighlightPopover';
import { useTranslationSuggestion } from '../hooks/useTranslationSuggestion';
import type { TextSegment } from '../types';

type HighlightSelection = {
  selection: string;
  segmentId: number;
  reference: string;
  position: { top: number; left: number };
  containerWidth: number;
};

export default function TextReader() {
  const { urn } = useParams<{ urn: string }>();
  const [selectedWord, setSelectedWord] = useState<{
    word: string;
    language: string;
    segmentId: number;
  } | null>(null);
  const [highlightSelection, setHighlightSelection] = useState<HighlightSelection | null>(null);
  const textContainerRef = useRef<HTMLDivElement>(null);
  const tutorFlag = String(import.meta.env.VITE_ENABLE_TUTOR ?? 'true').toLowerCase();
  const tutorFeatureEnabled = tutorFlag !== 'false' && tutorFlag !== '0';

  const {
    mutate: requestTranslationSuggestion,
    data: tutorSuggestion,
    isPending: isTutorPending,
    reset: resetTutorSuggestion,
    error: tutorError,
  } = useTranslationSuggestion();

  useEffect(() => {
    if (!tutorFeatureEnabled) {
      setHighlightSelection(null);
      resetTutorSuggestion();
    }
  }, [tutorFeatureEnabled, resetTutorSuggestion]);

  const clearHighlight = () => {
    setHighlightSelection(null);
    resetTutorSuggestion();
    const selection = window.getSelection();
    if (selection?.removeAllRanges) {
      selection.removeAllRanges();
    }
  };
  
  const { data, isLoading } = useQuery({
    queryKey: ['text', urn],
    queryFn: () => textApi.get(urn!),
    enabled: !!urn,
  });

  const handleWordClick = (word: string, segmentId: number) => {
    if (!data?.data.text) return;
    clearHighlight();
    
    // Clean punctuation from word
    const cleanWord = word.replace(/[.,;:!?·\[\]()]/g, '').trim();
    if (!cleanWord) return;
    
    setSelectedWord({
      word: cleanWord,
      language: data.data.text.language,
      segmentId,
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-600 border-t-transparent mb-4"></div>
          <p className="text-gray-600">Loading text...</p>
        </div>
      </div>
    );
  }

  if (!data?.data) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-12">
        <div className="bg-red-50 border border-red-200 rounded-lg p-6 text-center">
          <p className="text-red-800">Text not found</p>
        </div>
      </div>
    );
  }

  const { text, segments } = data.data;
  const segmentMap = useMemo(() => {
    const map = new Map<number, TextSegment>();
    segments.forEach((segment) => map.set(segment.id, segment));
    return map;
  }, [segments]);

  const tutorErrorMessage = useMemo(() => {
    if (!tutorError) return null;
    const detail =
      (tutorError.response?.data as { detail?: string } | undefined)?.detail;
    return detail ?? tutorError.message;
  }, [tutorError]);

  const getSegmentElement = (node: Node | null): HTMLElement | null => {
    if (!node) return null;
    if (node instanceof HTMLElement) {
      return node.closest('[data-segment-id]');
    }
    if (node.parentElement) {
      return node.parentElement.closest('[data-segment-id]');
    }
    return null;
  };

  const handleTextHighlight = () => {
    if (!tutorFeatureEnabled || !textContainerRef.current) return;
    const selection = window.getSelection();
    if (!selection) return;

    if (selection.isCollapsed) {
      clearHighlight();
      return;
    }

    const rawText = selection.toString().replace(/\s+/g, ' ').trim();
    if (!rawText) {
      clearHighlight();
      return;
    }

    const segmentElement =
      getSegmentElement(selection.anchorNode) ??
      getSegmentElement(selection.focusNode);

    if (!segmentElement) return;

    const segmentIdAttr = segmentElement.getAttribute('data-segment-id');
    if (!segmentIdAttr) return;

    const segmentId = Number(segmentIdAttr);
    if (Number.isNaN(segmentId)) return;

    const reference =
      segmentElement.getAttribute('data-segment-reference') ??
      segmentMap.get(segmentId)?.reference ??
      '';

    if (selection.rangeCount === 0) return;

    const container = textContainerRef.current;
    const range = selection.getRangeAt(0);
    const rangeRect = range.getBoundingClientRect();
    const containerRect = container.getBoundingClientRect();

    const top =
      rangeRect.bottom - containerRect.top + container.scrollTop + 8;
    const left =
      rangeRect.left - containerRect.left + container.scrollLeft;

    setHighlightSelection({
      selection: rawText,
      segmentId,
      reference,
      position: { top, left },
      containerWidth: container.clientWidth,
    });
    resetTutorSuggestion();
  };

  const handleAskTutor = () => {
    if (!highlightSelection) return;

    requestTranslationSuggestion({
      text_id: text.id,
      segment_id: highlightSelection.segmentId,
      selection: highlightSelection.selection,
      language: text.language,
      metadata: {
        segment_reference: highlightSelection.reference,
        selection_length: highlightSelection.selection.length,
      },
    });
  };

  const handleScroll = () => {
    if (highlightSelection) {
      clearHighlight();
    }
  };

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Main text area */}
      <div
        className="flex-1 overflow-y-auto relative"
        ref={textContainerRef}
        onMouseUp={handleTextHighlight}
        onScroll={handleScroll}
      >
        <div className="max-w-4xl mx-auto px-8 py-8">
          {/* Header */}
          <div className="mb-8 pb-8 border-b">
            <h1 className="text-4xl font-bold mb-2">{text.title}</h1>
            <h2 className="text-2xl text-gray-600 mb-4">{text.author}</h2>
            {text.is_fragment && (
              <div className="flex items-center gap-2 text-yellow-700 bg-yellow-50 p-3 rounded-lg">
                <span className="text-xl">⚠️</span>
                <span>This is a fragmentary text</span>
              </div>
            )}
            {!tutorFeatureEnabled && (
              <div className="mt-4 rounded-lg border border-dashed border-gray-300 bg-gray-50 px-4 py-3 text-sm text-gray-600">
                Tutor suggestions are disabled in this environment.
              </div>
            )}
          </div>
          
          {/* Text content */}
          <div className="space-y-6">
            {segments.map((segment: TextSegment) => (
              <div
                key={segment.id}
                className="flex gap-6"
                data-segment-id={segment.id}
                data-segment-reference={segment.reference}
              >
                <div className="text-gray-400 w-16 text-right text-sm font-mono flex-shrink-0">
                  {segment.reference}
                </div>
                <div className="flex-1">
                  <div className="text-lg leading-relaxed greek-text">
                    {segment.content.split(/\s+/).map((word, idx) => (
                      <span
                        key={idx}
                        onClick={() => handleWordClick(word, segment.id)}
                        className="cursor-pointer hover:bg-blue-100 hover:shadow-sm px-1 py-0.5 rounded transition-colors inline-block"
                      >
                        {word}{' '}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>

          {segments.length === 0 && (
            <div className="text-center py-12 text-gray-500">
              No text segments available
            </div>
          )}
        </div>
        {tutorFeatureEnabled && highlightSelection && (
          <HighlightPopover
            selection={highlightSelection.selection}
            reference={highlightSelection.reference}
            position={highlightSelection.position}
            containerWidth={highlightSelection.containerWidth}
            onAskTutor={handleAskTutor}
            onClose={clearHighlight}
            isLoading={isTutorPending}
            suggestion={tutorSuggestion}
            errorMessage={tutorErrorMessage}
          />
        )}
      </div>
      
      {/* Side panel */}
      {selectedWord && (
        <WordAnalysisPanel
          word={selectedWord.word}
          language={selectedWord.language}
          segmentId={selectedWord.segmentId}
          textId={text.id}
          onClose={() => setSelectedWord(null)}
        />
      )}
    </div>
  );
}

