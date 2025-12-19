import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import WordAnalysisPanel from './WordAnalysisPanel';
import { annotationApi } from '../services/api';
import type { Annotation, TranslationCard } from '../types';

interface Props {
  selectedWord: {
    word: string;
    language: string;
    segmentId: number;
  } | null;
  textId: number;
  onCloseWord: () => void;
  onNoteClick?: (word: string, segmentId: number) => void;
  translationCards?: TranslationCard[];
  onDeleteCard?: (cardId: string) => void;
}

export default function ToolsPanel({ selectedWord, textId, onCloseWord, onNoteClick, translationCards = [], onDeleteCard }: Props) {
  const [activeTab, setActiveTab] = useState<'morphology' | 'notes'>('morphology');
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [editingNoteId, setEditingNoteId] = useState<number | null>(null);
  const [editedNote, setEditedNote] = useState('');
  const queryClient = useQueryClient();

  // Fetch all annotations for this text
  const { data: annotations, isLoading: annotationsLoading } = useQuery({
    queryKey: ['text-annotations', textId],
    queryFn: () => annotationApi.list({ text_id: textId }),
    enabled: !!textId,
  });

  // Delete annotation mutation
  const deleteAnnotation = useMutation({
    mutationFn: (id: number) => annotationApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['text-annotations', textId] });
      queryClient.invalidateQueries({ queryKey: ['annotations'] });
    },
  });

  // Update annotation mutation
  const updateAnnotation = useMutation({
    mutationFn: ({ id, note }: { id: number; note: string }) => 
      annotationApi.update(id, note),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['text-annotations', textId] });
      queryClient.invalidateQueries({ queryKey: ['annotations'] });
      setEditingNoteId(null);
      setEditedNote('');
    },
  });

  const handleNoteClick = (annotation: Annotation) => {
    if (onNoteClick) {
      onNoteClick(annotation.word, annotation.segment_id);
    }
    setActiveTab('morphology');
  };

  const startEditing = (annotation: Annotation) => {
    setEditingNoteId(annotation.id);
    setEditedNote(annotation.note);
  };

  const cancelEditing = () => {
    setEditingNoteId(null);
    setEditedNote('');
  };

  const saveEdit = (id: number) => {
    if (editedNote.trim()) {
      updateAnnotation.mutate({ id, note: editedNote });
    }
  };

  const allAnnotations = annotations?.data || [];

  // When a NEW word is selected, switch to morphology tab and expand if collapsed
  // This only triggers when selectedWord changes, not on every render
  useEffect(() => {
    if (selectedWord) {
      setActiveTab('morphology');
      setIsCollapsed(false);
    }
  }, [selectedWord?.word, selectedWord?.segmentId]);

  // When a NEW translation card is added, switch to notes tab and expand
  const [prevCardCount, setPrevCardCount] = useState(0);
  useEffect(() => {
    if (translationCards.length > prevCardCount) {
      setActiveTab('notes');
      setIsCollapsed(false);
    }
    setPrevCardCount(translationCards.length);
  }, [translationCards.length, prevCardCount]);

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
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
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
          className={`flex-1 py-3 text-sm font-medium border-b-2 transition-colors relative ${
            activeTab === 'notes' 
              ? 'text-helios-teal border-helios-teal' 
              : 'text-gray-500 border-transparent hover:text-gray-700 hover:bg-gray-50'
          }`}
        >
          Notes
          {allAnnotations.length > 0 && (
            <span className="ml-1.5 px-1.5 py-0.5 text-xs rounded-full bg-helios-gold/20 text-helios-gold">
              {allAnnotations.length}
            </span>
          )}
        </button>
        <button
          onClick={() => setIsCollapsed(true)}
          className="px-3 py-3 text-gray-400 hover:text-gray-600 hover:bg-gray-50 transition-colors"
          title="Collapse Panel"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
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
        <div className={activeTab === 'notes' ? 'flex flex-col h-full overflow-y-auto' : 'hidden'}>
          <div className="p-4 space-y-4">
            {/* Translation Cards Section */}
            {translationCards.length > 0 && (
              <div className="space-y-3">
                <p className="text-xs text-helios-teal uppercase font-semibold flex items-center gap-1.5">
                  <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
                  </svg>
                  AI Translations ({translationCards.length})
                </p>
                {translationCards.map((card) => (
                  <div 
                    key={card.id} 
                    className="bg-gradient-to-br from-helios-teal/5 to-helios-teal/10 rounded-lg border border-helios-teal/20 shadow-sm overflow-hidden"
                  >
                    {/* Source text */}
                    <div className="px-3 py-2 bg-white/50 border-b border-helios-teal/10">
                      <p className="text-sm font-medium text-gray-800 greek-text line-clamp-2">
                        {card.source_text}
                      </p>
                    </div>
                    
                    {/* Translation content */}
                    <div className="p-3 space-y-2">
                      <p className="text-sm text-gray-800 font-medium">
                        {card.translation}
                      </p>
                      
                      {card.literal_gloss && (
                        <p className="text-xs text-gray-600">
                          <span className="font-semibold">Literal:</span> {card.literal_gloss}
                        </p>
                      )}
                      
                      <p className="text-xs text-gray-600 leading-relaxed">
                        {card.rationale}
                      </p>
                      
                      <div className="flex items-center justify-between pt-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs text-helios-teal bg-helios-teal/10 px-1.5 py-0.5 rounded">
                            {Math.round(card.confidence * 100)}% confident
                          </span>
                          <span className="text-xs text-gray-400">
                            {new Date(card.created_at).toLocaleTimeString()}
                          </span>
                        </div>
                        {onDeleteCard && (
                          <button
                            onClick={() => onDeleteCard(card.id)}
                            className="text-xs text-gray-400 hover:text-red-600 transition"
                          >
                            Dismiss
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Word Annotations Section */}
            {annotationsLoading ? (
              <div className="text-center py-8">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-helios-teal border-t-transparent"></div>
                <p className="mt-2 text-sm text-gray-500">Loading notes...</p>
              </div>
            ) : allAnnotations.length > 0 ? (
              <div className="space-y-3">
                <p className="text-xs text-gray-500 uppercase font-semibold">
                  Your Notes ({allAnnotations.length})
                </p>
                {allAnnotations.map((annotation: Annotation) => (
                  <div 
                    key={annotation.id} 
                    className="bg-white rounded-lg border border-gray-200 shadow-sm overflow-hidden"
                  >
                    {/* Note Header - Clickable Word */}
                    <button
                      onClick={() => handleNoteClick(annotation)}
                      className="w-full px-3 py-2 bg-gray-50 border-b border-gray-100 flex items-center justify-between hover:bg-gray-100 transition-colors"
                    >
                      <span className="font-medium text-helios-teal greek-text">
                        {annotation.word}
                      </span>
                      <span className="text-xs text-gray-400">
                        Line {annotation.segment_id}
                      </span>
                    </button>
                    
                    {/* Note Content */}
                    <div className="p-3">
                      {editingNoteId === annotation.id ? (
                        <div className="space-y-2">
                          <textarea
                            value={editedNote}
                            onChange={(e) => setEditedNote(e.target.value)}
                            className="w-full px-2 py-1.5 text-sm border border-gray-300 rounded focus:ring-2 focus:ring-helios-teal focus:border-transparent resize-none"
                            rows={3}
                            autoFocus
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => saveEdit(annotation.id)}
                              disabled={updateAnnotation.isPending}
                              className="flex-1 py-1.5 text-xs bg-helios-teal text-white rounded hover:bg-helios-teal/90 disabled:bg-gray-300 transition"
                            >
                              {updateAnnotation.isPending ? 'Saving...' : 'Save'}
                            </button>
                            <button
                              onClick={cancelEditing}
                              className="px-3 py-1.5 text-xs bg-gray-200 text-gray-700 rounded hover:bg-gray-300 transition"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <>
                          <p className="text-sm text-gray-700 mb-2">
                            {annotation.note}
                          </p>
                          <div className="flex items-center justify-between">
                            <span className="text-xs text-gray-400">
                              {new Date(annotation.created_at).toLocaleDateString()}
                            </span>
                            <div className="flex gap-2">
                              <button
                                onClick={() => startEditing(annotation)}
                                className="text-xs text-gray-500 hover:text-helios-teal transition"
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => deleteAnnotation.mutate(annotation.id)}
                                className="text-xs text-gray-500 hover:text-red-600 transition"
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : translationCards.length === 0 ? (
              <div className="text-center py-12 text-gray-400">
                <svg className="w-12 h-12 mx-auto mb-4 text-gray-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                <p className="mb-2">No notes yet</p>
                <p className="text-sm">Click a word and use "Add Note" in the Morphology tab, or use the AI toggle to translate passages.</p>
              </div>
            ) : null}
          </div>
        </div>

      </div>
    </aside>
  );
}
