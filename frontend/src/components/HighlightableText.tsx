import { useState, useRef } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { studyApi } from '../services/api';
import type { Highlight } from '../types';

interface Props {
  textId: number;
  segmentId: number;
  content: string;
  highlights: Highlight[];
  onWordClick: (word: string) => void;
}

export default function HighlightableText({ textId, segmentId, content, highlights, onWordClick }: Props) {
  const [selection, setSelection] = useState<{
    start: number;
    end: number;
    text: string;
    rect: DOMRect;
  } | null>(null);
  
  const containerRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const createHighlight = useMutation({
    mutationFn: (color: string) => {
      if (!selection) throw new Error('No selection');
      return studyApi.createHighlight({
        text_id: textId,
        segment_id: segmentId,
        start_offset: selection.start,
        end_offset: selection.end,
        selected_text: selection.text,
        color,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['highlights'] });
      setSelection(null);
      window.getSelection()?.removeAllRanges();
    },
  });

  const deleteHighlight = useMutation({
    mutationFn: (id: number) => studyApi.deleteHighlight(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['highlights'] });
    },
  });

  // Since accurate highlighting on a mixed DOM (text + spans) is complex to implement from scratch
  // without a library, and we want to be robust:
  // We will implement a render-time highlighting approach.
  // 1. We have the raw `content` string.
  // 2. We have a list of `highlights` with start/end offsets.
  // 3. We sort highlights by start offset.
  // 4. We slice the content string into parts: [text, highlight, text, highlight, text]
  // 5. We map these parts to spans.

  // Handling creation of NEW highlights:
  // We need to map the DOM selection back to string indices.
  // We can do this by traversing the text nodes in the container and counting characters until we reach the selection start.

  const getSelectionOffsets = (): { start: number; end: number } | null => {
    const sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return null;

    const range = sel.getRangeAt(0);
    const container = containerRef.current;
    if (!container) return null;

    // Create a range that spans from the start of the container to the start of the selection
    const preSelectionRange = range.cloneRange();
    preSelectionRange.selectNodeContents(container);
    preSelectionRange.setEnd(range.startContainer, range.startOffset);
    
    const start = preSelectionRange.toString().length;
    const end = start + range.toString().length;
    
    return { start, end };
  };
  
  const onMouseUp = () => {
    const offsets = getSelectionOffsets();
    const sel = window.getSelection();
    
    if (offsets && sel && !sel.isCollapsed) {
        const text = sel.toString();
        if (text.trim().length > 0) {
            const rect = sel.getRangeAt(0).getBoundingClientRect();
            setSelection({
                start: offsets.start,
                end: offsets.end,
                text: text,
                rect
            });
        }
    } else {
        setSelection(null);
    }
  };

  // Sort highlights
  const sortedHighlights = [...highlights].sort((a, b) => a.start_offset - b.start_offset);

  // Render content with highlights
  // We need to handle overlaps or just flatten. For MVP, assume no overlaps or last-one-wins.
  // We'll rebuild the text from chunks.
  const renderContent = () => {
    const elements = [];
    let lastIndex = 0;

    sortedHighlights.forEach((highlight) => {
      // Safety check indices
      if (highlight.start_offset < lastIndex) return; // Skip overlapping for now
      if (highlight.start_offset > content.length) return;

      // Text before highlight
      if (highlight.start_offset > lastIndex) {
        const textPart = content.slice(lastIndex, highlight.start_offset);
        elements.push(
            <span key={`text-${lastIndex}`}>{renderWords(textPart)}</span>
        );
      }

      // Highlighted text
      const highlightText = content.slice(highlight.start_offset, highlight.end_offset);
      elements.push(
        <span
          key={`highlight-${highlight.id}`}
          className={`bg-${highlight.color}-200 hover:bg-${highlight.color}-300 cursor-pointer transition-colors rounded px-0.5`}
          title="Click to remove highlight"
          onClick={(e) => {
            e.stopPropagation(); // Prevent word analysis
            if (confirm('Remove highlight?')) {
                deleteHighlight.mutate(highlight.id);
            }
          }}
        >
          {renderWords(highlightText)}
        </span>
      );

      lastIndex = highlight.end_offset;
    });

    // Remaining text
    if (lastIndex < content.length) {
      const textPart = content.slice(lastIndex);
        elements.push(
            <span key={`text-${lastIndex}`}>{renderWords(textPart)}</span>
        );
    }

    return elements;
  };

  // Helper to render individual words within a block (to keep word analysis working)
  const renderWords = (text: string) => {
    return text.split(/(\s+)/).map((part, idx) => {
      // Calculate approximate offset for this word (not used for now, but good for future)
      if (part.match(/\s+/)) return <span key={idx}>{part}</span>;
      if (!part) return null;

      return (
        <span
          key={idx}
          onClick={() => {
             // Only analyze if not selecting text
             if (window.getSelection()?.toString().length === 0) {
                 onWordClick(part);
             }
          }}
          className="cursor-pointer hover:text-blue-600 hover:underline"
        >
          {part}
        </span>
      );
    });
  };

  return (
    <div className="relative" ref={containerRef} onMouseUp={onMouseUp}>
      <div className="text-lg leading-relaxed greek-text" style={{ fontFamily: 'GFS Didot, Georgia, serif' }}>
        {renderContent()}
      </div>

      {/* Selection Popover */}
      {selection && (
        <div
          className="absolute z-50 flex gap-1 bg-white shadow-lg rounded p-1 border"
          style={{
            top: `${selection.rect.top + window.scrollY - 40}px`, // Position above selection (naive)
            left: `${selection.rect.left + window.scrollX}px`,
          }}
        >
            {/* Color buttons */}
            {['yellow', 'green', 'pink', 'blue'].map(color => (
                <button
                    key={color}
                    onClick={() => createHighlight.mutate(color)}
                    className={`w-6 h-6 rounded-full bg-${color}-200 hover:bg-${color}-300 border border-gray-300`}
                    title={`Highlight ${color}`}
                />
            ))}
        </div>
      )}
    </div>
  );
}

