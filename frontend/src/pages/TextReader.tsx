import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { textApi } from '../services/api';
import WordAnalysisPanel from '../components/WordAnalysisPanel';
import type { TextSegment } from '../types';

export default function TextReader() {
  const { urn } = useParams<{ urn: string }>();
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

