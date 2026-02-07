import { useCallback, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { textApi } from '../services/api';
import SourcesSidebar from '../components/SourcesSidebar';
import ToolsPanel from '../components/ToolsPanel';
import TranslationAssistToggle from '../components/TranslationAssistToggle';
import { useTranslationAssist } from '../hooks/useTranslationAssist';
import type { TextSegment, TranslationCard } from '../types';

export default function TextReader() {
  const { urn } = useParams<{ urn: string }>();
  const [selectedWord, setSelectedWord] = useState<{
    word: string;
    language: string;
    segmentId: number;
  } | null>(null);
  const [aiModeActive, setAiModeActive] = useState(false);
  const [translationCards, setTranslationCards] = useState<TranslationCard[]>([]);
  const textContainerRef = useRef<HTMLDivElement>(null);

  const {
    mutate: requestTranslation,
    isPending: isTranslating,
    error: translationError,
  } = useTranslationAssist();

  const clearSelection = useCallback(() => {
    const selection = window.getSelection();
    if (selection?.removeAllRanges) {
      selection.removeAllRanges();
    }
  }, []);
  
  const { data, isLoading } = useQuery({
    queryKey: ['text', urn],
    queryFn: () => textApi.get(urn!),
    enabled: !!urn,
  });

  // These hooks must be called before any early returns to maintain consistent hook order
  const segments = data?.data?.segments ?? [];
  const text = data?.data?.text;

  const translationErrorMessage = useMemo(() => {
    if (!translationError) return null;
    const detail =
      (translationError.response?.data as { detail?: string } | undefined)?.detail;
    return detail ?? translationError.message;
  }, [translationError]);

  const handleWordClick = (word: string, segmentId: number) => {
    if (!text) return;
    clearSelection();
    
    // Clean punctuation from word
    const cleanWord = word.replace(/[.,;:!?·\[\]()]/g, '').trim();
    if (!cleanWord) return;
    
    setSelectedWord({
      word: cleanWord,
      language: text.language,
      segmentId,
    });
  };

  // Handler for when user clicks a note in the Notes tab
  const handleNoteClick = (word: string, segmentId: number) => {
    if (!text) return;
    
    setSelectedWord({
      word,
      language: text.language,
      segmentId,
    });
    
    // Scroll to the segment
    const segmentElement = document.querySelector(`[data-segment-id="${segmentId}"]`);
    if (segmentElement) {
      segmentElement.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-full w-full">
        <SourcesSidebar />
        <div className="flex-1 flex items-center justify-center bg-white">
          <div className="text-center">
            <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-600 border-t-transparent mb-4"></div>
            <p className="text-gray-600">Loading text...</p>
          </div>
        </div>
        <ToolsPanel selectedWord={null} textId={0} onCloseWord={() => {}} />
      </div>
    );
  }

  if (!data?.data || !text) {
    return (
       <div className="flex h-full w-full">
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

  // Handle AI translation when text is selected in AI mode
  const handleTextSelection = () => {
    if (!aiModeActive || !textContainerRef.current || !text) return;

    const selection = window.getSelection();
    if (!selection || selection.isCollapsed) return;

    const rawText = selection.toString().replace(/\s+/g, ' ').trim();
    if (!rawText) return;

    // Validate length (max ~600 chars / 1 paragraph)
    if (rawText.length > 600) {
      alert('Please select a shorter passage (max ~1 paragraph).');
      clearSelection();
      return;
    }

    // Send to translation API
    requestTranslation(
      { text: rawText, language: text.language },
      {
        onSuccess: (result) => {
          // Add to translation cards
          const newCard: TranslationCard = {
            id: `card-${Date.now()}`,
            source_text: result.source_text,
            translation: result.translation,
            literal_gloss: result.literal_gloss,
            rationale: result.rationale,
            confidence: result.confidence,
            language: result.language,
            created_at: new Date().toISOString(),
          };
          setTranslationCards((prev) => [newCard, ...prev]);
          clearSelection();
        },
        onError: () => {
          clearSelection();
        },
      }
    );
  };

  const handleAiToggle = () => {
    setAiModeActive((prev) => !prev);
    if (aiModeActive) {
      clearSelection();
    }
  };

  const handleDeleteCard = (cardId: string) => {
    setTranslationCards((prev) => prev.filter((c) => c.id !== cardId));
  };

  return (
    <div className="flex h-full w-full">
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
            <div className="flex items-center gap-3 shrink-0">
                {/* AI Translation Toggle */}
                <TranslationAssistToggle
                  isActive={aiModeActive}
                  onToggle={handleAiToggle}
                  isLoading={isTranslating}
                />
                {/* Error toast */}
                {translationErrorMessage && (
                  <span className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded">
                    {translationErrorMessage}
                  </span>
                )}
            </div>
        </div>

        {/* Scrollable Text Area */}
        <div
            className={`flex-1 overflow-y-auto relative ${aiModeActive ? 'cursor-crosshair' : ''}`}
            ref={textContainerRef}
            onMouseUp={handleTextSelection}
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

            {/* AI Mode indicator */}
            {aiModeActive && (
              <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-gradient-to-r from-helios-teal to-helios-teal-dark text-white px-4 py-2 rounded-full shadow-lg text-sm flex items-center gap-2 z-40">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                </svg>
                <span>Select text to translate</span>
                {isTranslating && <span className="animate-pulse">...</span>}
              </div>
            )}
        </div>
      </div>
      
      {/* Right Panel: Tools */}
      <ToolsPanel 
        selectedWord={selectedWord} 
        textId={text.id} 
        onCloseWord={() => setSelectedWord(null)}
        onNoteClick={handleNoteClick}
        translationCards={translationCards}
        onDeleteCard={handleDeleteCard}
      />
    </div>
  );
}
