import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { textApi } from '../services/api';
import SourcesSidebar from '../components/SourcesSidebar';
import ToolsPanel from '../components/ToolsPanel';
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

  // These hooks must be called before any early returns to maintain consistent hook order
  const segments = data?.data?.segments ?? [];
  const text = data?.data?.text;

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

  const handleWordClick = (word: string, segmentId: number) => {
    if (!text) return;
    clearHighlight();
    
    // Clean punctuation from word
    const cleanWord = word.replace(/[.,;:!?·\[\]()]/g, '').trim();
    if (!cleanWord) return;
    
    setSelectedWord({
      word: cleanWord,
      language: text.language,
      segmentId,
    });
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-600 border-t-transparent mb-4"></div>
          <p className="text-gray-600">Loading text...</p>
        </div>
      </div>
    );
  }

  if (!data?.data || !text) {
    return (
       <div className="flex h-full">
            <SourcesSidebar />
            <div className="flex-1 flex items-center justify-center bg-gray-50">
                <div className="bg-white border border-red-200 rounded-lg p-6 text-center shadow-sm">
                    <p className="text-red-800 font-medium">Text not found</p>
                    <p className="text-gray-600 text-sm mt-2">Please select a text from the sidebar.</p>
                </div>
            </div>
            <ToolsPanel selectedWord={null} textId={0} onCloseWord={() => {}} />
      </div>
    );
  }

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
    <div className="flex h-full">
      {/* Left Panel: Sources */}
      <SourcesSidebar />

      {/* Middle Panel: Reader */}
      <div className="flex-1 flex flex-col min-w-0 bg-white relative shadow-sm z-0">
        
        {/* Breadcrumbs / Toolbar */}
        <div className="h-12 border-b border-gray-100 flex items-center px-6 justify-between bg-white shrink-0">
            <div className="flex items-center text-sm text-gray-500 gap-2 overflow-hidden">
                <span className="truncate">{text.author}</span>
                <svg className="w-4 h-4 flex-shrink-0 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7"></path></svg>
                <span className="text-gray-900 font-medium truncate">{text.title}</span>
            </div>
            <div className="flex items-center gap-2 shrink-0">
                {/* Zoom controls could go here */}
            </div>
        </div>

        {/* Scrollable Text Area */}
        <div
            className="flex-1 overflow-y-auto relative"
            ref={textContainerRef}
            onMouseUp={handleTextHighlight}
            onScroll={handleScroll}
        >
            <div className="max-w-3xl mx-auto px-8 py-12">
                {/* Header Content */}
                <div className="mb-12 text-center">
                    <h1 className="text-4xl font-serif font-bold text-gray-900 mb-4">{text.title}</h1>
                    <h2 className="text-xl text-gray-600 font-serif italic">{text.author}</h2>
                    {text.is_fragment && (
                    <div className="mt-4 inline-flex items-center gap-2 text-yellow-700 bg-yellow-50 px-4 py-2 rounded-full text-sm">
                        <span>⚠️ Fragmentary Text</span>
                    </div>
                    )}
                </div>

                {/* Text Segments */}
                <div className="space-y-6 text-xl leading-loose text-gray-800 greek-text">
                    {segments.map((segment: TextSegment) => (
                    <div
                        key={segment.id}
                        className="flex gap-6 group"
                        data-segment-id={segment.id}
                        data-segment-reference={segment.reference}
                    >
                        <div className="text-gray-300 w-8 text-right text-xs font-sans pt-2 select-none group-hover:text-gray-400 transition-colors">
                            {segment.reference}
                        </div>
                        <div className="flex-1">
                            <p>
                                {segment.content.split(/\s+/).map((word, idx) => (
                                <span
                                    key={idx}
                                    onClick={(e) => {
                                        e.stopPropagation(); // Prevent highlight handler from firing awkwardly
                                        handleWordClick(word, segment.id);
                                    }}
                                    className={`cursor-pointer rounded px-0.5 transition-colors inline-block ${
                                        selectedWord?.word === word.replace(/[.,;:!?·\[\]()]/g, '').trim() && selectedWord?.segmentId === segment.id
                                        ? 'bg-blue-200 text-blue-900'
                                        : 'hover:bg-blue-50'
                                    }`}
                                >
                                    {word}{' '}
                                </span>
                                ))}
                            </p>
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

            {/* Popover for Tutor */}
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
      </div>
      
      {/* Right Panel: Tools */}
      <ToolsPanel 
        selectedWord={selectedWord} 
        textId={text.id} 
        onCloseWord={() => setSelectedWord(null)} 
      />
    </div>
  );
}
