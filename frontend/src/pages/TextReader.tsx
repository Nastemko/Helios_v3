import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { textApi, studyApi } from '../services/api';
import WordAnalysisPanel from '../components/WordAnalysisPanel';
import Notepad from '../components/Notepad';
import HighlightableText from '../components/HighlightableText';
import type { TextSegment, Highlight } from '../types';

export default function TextReader() {
  const { urn } = useParams<{ urn: string }>();
  const [showNotepad, setShowNotepad] = useState(false);
  const [selectedWord, setSelectedWord] = useState<{
    word: string;
    language: string;
    segmentId: number;
  } | null>(null);
  
  const { data, isLoading } = useQuery({
    queryKey: ['text', urn],
    queryFn: () => textApi.get(urn!),
    enabled: !!urn,
  });

  const { data: highlights } = useQuery({
    queryKey: ['highlights', data?.data.text.id],
    queryFn: () => studyApi.getHighlights({ text_id: data?.data.text.id }),
    enabled: !!data?.data.text.id,
  });

  const handleWordClick = (word: string, segmentId: number) => {
    if (!data?.data.text) return;
    
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

  return (
    <div className="flex h-[calc(100vh-4rem)]">
      {/* Main text area */}
      <div className="flex-1 overflow-y-auto">
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
          </div>
          
          {/* Text content */}
          <div className="space-y-6">
            {segments.map((segment: TextSegment) => (
              <div key={segment.id} className="flex gap-6">
                <div className="text-gray-400 w-16 text-right text-sm font-mono flex-shrink-0">
                  {segment.reference}
                </div>
                <div className="flex-1">
                  <HighlightableText
                    textId={text.id}
                    segmentId={segment.id}
                    content={segment.content}
                    highlights={highlights?.data.filter((h: Highlight) => h.segment_id === segment.id) || []}
                    onWordClick={(word) => handleWordClick(word, segment.id)}
                  />
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

      {/* Notepad Toggle */}
      <button
        onClick={() => setShowNotepad(!showNotepad)}
        className="fixed bottom-8 right-8 w-12 h-12 bg-yellow-400 hover:bg-yellow-500 rounded-full shadow-lg flex items-center justify-center text-2xl z-40 transition-transform hover:scale-110"
        title="Toggle Notepad"
      >
        📝
      </button>

      {/* Notepad */}
      <Notepad
        textId={text.id}
        isOpen={showNotepad}
        onClose={() => setShowNotepad(false)}
      />
    </div>
  );
}

