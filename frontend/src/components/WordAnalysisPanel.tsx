import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { analysisApi, annotationApi } from '../services/api';
import type { Annotation } from '../types';

interface Props {
  word: string;
  language: string;
  segmentId: number;
  textId: number;
  onClose: () => void;
}

export default function WordAnalysisPanel({ word, language, segmentId, textId, onClose }: Props) {
  const [note, setNote] = useState('');
  const [showNoteForm, setShowNoteForm] = useState(false);
  const queryClient = useQueryClient();
  
  // Fetch word analysis
  const { data: analysis, isLoading: analysisLoading } = useQuery({
    queryKey: ['word-analysis', word, language],
    queryFn: () => analysisApi.analyzeWord(word, language),
  });
  
  // Fetch user's annotations for this segment
  const { data: annotations } = useQuery({
    queryKey: ['annotations', textId, segmentId],
    queryFn: () => annotationApi.list({ text_id: textId, segment_id: segmentId }),
  });
  
  // Create annotation mutation
  const createAnnotation = useMutation({
    mutationFn: (noteText: string) =>
      annotationApi.create({
        text_id: textId,
        segment_id: segmentId,
        word,
        note: noteText,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['annotations'] });
      setNote('');
      setShowNoteForm(false);
    },
  });
  
  // Delete annotation mutation
  const deleteAnnotation = useMutation({
    mutationFn: (id: number) => annotationApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['annotations'] });
    },
  });

  const wordAnnotations = annotations?.data?.filter(
    (a: Annotation) => a.word === word
  ) || [];

  return (
    <div className="w-96 border-l bg-white overflow-y-auto shadow-lg">
      <div className="sticky top-0 bg-white border-b z-10">
        <div className="flex justify-between items-center p-4">
          <h2 className="text-xl font-bold greek-text">{word}</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition p-1"
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      </div>

      <div className="p-4 space-y-6">
        {analysisLoading ? (
          <div className="text-center py-8">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-600 border-t-transparent"></div>
            <p className="mt-2 text-sm text-gray-600">Analyzing...</p>
          </div>
        ) : analysis?.data ? (
          <>
            {/* Lemma */}
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase mb-1">Lemma</h3>
              <p className="text-xl greek-text font-medium">{analysis.data.lemma}</p>
            </div>
            
            {/* Part of Speech */}
            <div>
              <h3 className="text-xs font-semibold text-gray-500 uppercase mb-1">Part of Speech</h3>
              <p className="text-lg capitalize">{analysis.data.pos}</p>
            </div>
            
            {/* Morphology */}
            {Object.keys(analysis.data.morphology).length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Morphology</h3>
                <div className="space-y-1">
                  {Object.entries(analysis.data.morphology).map(([key, value]) => (
                    <div key={key} className="flex justify-between text-sm">
                      <span className="text-gray-600 capitalize">{key}:</span>
                      <span className="font-medium">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
            
            {/* Definitions */}
            {analysis.data.definitions.length > 0 && (
              <div>
                <h3 className="text-xs font-semibold text-gray-500 uppercase mb-2">Definitions</h3>
                <ul className="space-y-2">
                  {analysis.data.definitions.map((def, idx) => (
                    <li key={idx} className="text-sm text-gray-700">
                      {idx + 1}. {def}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            
            {/* Lexicon Link */}
            <div>
              <a
                href={analysis.data.lexicon_url}
                target="_blank"
                rel="noopener noreferrer"
                className="block w-full py-2 px-4 bg-blue-600 text-white text-center rounded-lg hover:bg-blue-700 transition font-medium"
              >
                View Full Lexicon Entry →
              </a>
            </div>

            {analysis.data.perseus_url && (
              <div>
                <a
                  href={analysis.data.perseus_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block w-full py-2 px-4 bg-gray-100 text-gray-700 text-center rounded-lg hover:bg-gray-200 transition text-sm"
                >
                  Perseus Morphology →
                </a>
              </div>
            )}
          </>
        ) : (
          <div className="text-center py-8 text-gray-500">
            No analysis available
          </div>
        )}

        {/* Annotations Section */}
        <div className="border-t pt-6">
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-xs font-semibold text-gray-500 uppercase">Your Notes</h3>
            {!showNoteForm && (
              <button
                onClick={() => setShowNoteForm(true)}
                className="text-sm text-blue-600 hover:text-blue-700"
              >
                + Add Note
              </button>
            )}
          </div>
          
          {/* Existing annotations */}
          {wordAnnotations.length > 0 && (
            <div className="space-y-2 mb-3">
              {wordAnnotations.map((annotation: Annotation) => (
                <div key={annotation.id} className="p-3 bg-gray-50 rounded-lg">
                  <p className="text-sm text-gray-700 mb-2">{annotation.note}</p>
                  <div className="flex justify-between items-center">
                    <span className="text-xs text-gray-500">
                      {new Date(annotation.created_at).toLocaleDateString()}
                    </span>
                    <button
                      onClick={() => deleteAnnotation.mutate(annotation.id)}
                      className="text-xs text-red-600 hover:text-red-700"
                    >
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          {/* Add new annotation */}
          {showNoteForm && (
            <div className="space-y-2">
              <textarea
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Add a personal note or translation..."
                className="w-full px-3 py-2 border border-gray-300 rounded-lg resize-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                rows={3}
                autoFocus
              />
              <div className="flex gap-2">
                <button
                  onClick={() => createAnnotation.mutate(note)}
                  disabled={!note.trim() || createAnnotation.isPending}
                  className="flex-1 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition text-sm font-medium"
                >
                  {createAnnotation.isPending ? 'Saving...' : 'Save Note'}
                </button>
                <button
                  onClick={() => {
                    setShowNoteForm(false);
                    setNote('');
                  }}
                  className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition text-sm"
                >
                  Cancel
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

