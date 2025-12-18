import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { studyApi } from '../services/api';
import type { StudentNote } from '../types';

interface Props {
  textId?: number;
  isOpen: boolean;
  onClose: () => void;
}

export default function Notepad({ textId, isOpen, onClose }: Props) {
  const [newNote, setNewNote] = useState('');
  const queryClient = useQueryClient();

  const { data: notes, isLoading } = useQuery({
    queryKey: ['notes', textId],
    queryFn: () => studyApi.getNotes(textId),
    enabled: isOpen,
  });

  const createNote = useMutation({
    mutationFn: (content: string) =>
      studyApi.createNote({ text_id: textId, content }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] });
      setNewNote('');
    },
  });

  const deleteNote = useMutation({
    mutationFn: (id: number) => studyApi.deleteNote(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['notes'] });
    },
  });

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-4 right-4 w-80 bg-white rounded-lg shadow-xl border border-gray-200 flex flex-col h-96 z-50">
      <div className="flex justify-between items-center p-3 border-b bg-gray-50 rounded-t-lg">
        <h3 className="font-semibold text-gray-700">Notepad</h3>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600"
        >
          ✕
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-3 space-y-3">
        {isLoading ? (
          <p className="text-center text-gray-500 text-sm">Loading notes...</p>
        ) : notes?.data && notes.data.length > 0 ? (
          notes.data.map((note: StudentNote) => (
            <div key={note.id} className="bg-yellow-50 p-3 rounded border border-yellow-100 relative group">
              <p className="text-sm text-gray-800 whitespace-pre-wrap">{note.content}</p>
              <div className="mt-2 flex justify-between items-center text-xs text-gray-500">
                <span>{new Date(note.created_at).toLocaleDateString()}</span>
                <button
                  onClick={() => deleteNote.mutate(note.id)}
                  className="text-red-400 hover:text-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  Delete
                </button>
              </div>
            </div>
          ))
        ) : (
          <p className="text-center text-gray-400 text-sm italic">No notes yet. Add one below!</p>
        )}
      </div>

      <div className="p-3 border-t bg-gray-50 rounded-b-lg">
        <div className="flex gap-2">
          <textarea
            value={newNote}
            onChange={(e) => setNewNote(e.target.value)}
            placeholder="Type a note..."
            className="flex-1 p-2 text-sm border rounded resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
            rows={2}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                if (newNote.trim()) createNote.mutate(newNote);
              }
            }}
          />
          <button
            onClick={() => newNote.trim() && createNote.mutate(newNote)}
            disabled={!newNote.trim() || createNote.isPending}
            className="px-3 py-1 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed text-sm"
          >
            Add
          </button>
        </div>
      </div>
    </div>
  );
}

