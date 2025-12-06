import { useState } from 'react';
import WordAnalysisPanel from './WordAnalysisPanel';

interface Props {
  selectedWord: {
    word: string;
    language: string;
    segmentId: number;
  } | null;
  textId: number;
  onCloseWord: () => void;
}

export default function ToolsPanel({ selectedWord, textId, onCloseWord }: Props) {
  const [activeTab, setActiveTab] = useState<'morphology' | 'notes'>('morphology');

  // If a word is selected, switch to morphology tab automatically
  if (selectedWord && activeTab !== 'morphology') {
    setActiveTab('morphology');
  }

  return (
    <aside className="w-96 bg-white border-l border-gray-200 flex flex-col shrink-0 shadow-lg z-10 h-full">
      {/* Tabs */}
      <div className="flex border-b border-gray-200">
        <button 
            onClick={() => setActiveTab('morphology')} 
            className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'morphology' 
                ? 'text-blue-600 border-blue-600' 
                : 'text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-50'
            }`}
        >
            Morphology
        </button>
        <button 
            onClick={() => setActiveTab('notes')} 
            className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${
                activeTab === 'notes' 
                ? 'text-blue-600 border-blue-600' 
                : 'text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-50'
            }`}
        >
            Notes
        </button>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto bg-gray-50 relative">
        
        {/* Morphology View */}
        <div className={activeTab === 'morphology' ? 'block h-full' : 'hidden'}>
            {selectedWord ? (
                <WordAnalysisPanel
                    word={selectedWord.word}
                    language={selectedWord.language}
                    segmentId={selectedWord.segmentId}
                    textId={textId}
                    onClose={onCloseWord}
                    embedded={true} // New prop to tell component it's inside a container
                />
            ) : (
                <div className="text-center py-12 text-gray-400 px-4">
                    <p>Click a word in the text to see its morphological analysis.</p>
                </div>
            )}
        </div>

        {/* Notes View */}
        <div className={activeTab === 'notes' ? 'flex flex-col h-full p-4' : 'hidden'}>
             <div className="text-center py-12 text-gray-400">
                <p>General notes functionality coming soon.</p>
                <p className="text-sm mt-2">Use the Morphology tab to add notes to specific words.</p>
            </div>
        </div>

      </div>
    </aside>
  );
}

