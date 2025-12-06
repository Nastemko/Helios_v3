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
  const [isCollapsed, setIsCollapsed] = useState(false);

  // If a word is selected, switch to morphology tab and expand if collapsed
  if (selectedWord && activeTab !== 'morphology') {
    setActiveTab('morphology');
  }
  if (selectedWord && isCollapsed) {
    setIsCollapsed(false);
  }

  // Collapsed state - just show a thin bar with expand button
  if (isCollapsed) {
    return (
      <aside className="w-12 bg-white border-l border-gray-200 flex flex-col shrink-0 shadow-lg z-10 h-full">
        <button
          onClick={() => setIsCollapsed(false)}
          className="h-12 flex items-center justify-center hover:bg-gray-100 transition-colors"
          title="Expand Tools"
        >
          <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 19l-7-7 7-7M5 12h14" />
          </svg>
        </button>
        <div className="flex-1 flex items-center justify-center">
          <span className="text-xs text-gray-400 transform rotate-90 whitespace-nowrap">Tools</span>
        </div>
      </aside>
    );
  }

  return (
    <aside className="w-96 bg-white border-l border-gray-200 flex flex-col shrink-0 shadow-lg z-10 h-full">
      {/* Tabs */}
      <div className="flex border-b border-gray-200">
        <button 
          onClick={() => setActiveTab('morphology')} 
          className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'morphology' 
              ? 'text-helios-teal border-helios-teal' 
              : 'text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-50'
          }`}
        >
          Morphology
        </button>
        <button 
          onClick={() => setActiveTab('notes')} 
          className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'notes' 
              ? 'text-helios-teal border-helios-teal' 
              : 'text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-50'
          }`}
        >
          Notes
        </button>
        <button
          onClick={() => setIsCollapsed(true)}
          className="px-3 py-3 text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors"
          title="Collapse Panel"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
          </svg>
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
              embedded={true}
            />
          ) : (
            <div className="text-center py-12 text-gray-400 px-4">
              <svg className="w-12 h-12 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M15 15l-2 5L9 9l11 4-5 2zm0 0l5 5M7.188 2.239l.777 2.897M5.136 7.965l-2.898-.777M13.95 4.05l-2.122 2.122m-5.657 5.656l-2.12 2.122" />
              </svg>
              <p>Click a word in the text to see its analysis.</p>
            </div>
          )}
        </div>

        {/* Notes View */}
        <div className={activeTab === 'notes' ? 'flex flex-col h-full p-4' : 'hidden'}>
          <div className="text-center py-12 text-gray-400">
            <svg className="w-12 h-12 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            <p>General notes functionality coming soon.</p>
            <p className="text-sm mt-2">Use the Morphology tab to add notes to specific words.</p>
          </div>
        </div>

      </div>
    </aside>
  );
}
