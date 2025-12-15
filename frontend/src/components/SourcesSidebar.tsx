import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { textApi } from '../services/api';
import type { Text } from '../types';

export default function SourcesSidebar() {
  const { urn } = useParams<{ urn: string }>();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');
  const [isCollapsed, setIsCollapsed] = useState(false);

  const { data: texts, isLoading } = useQuery({
    queryKey: ['texts', search],
    queryFn: () => textApi.list({ search, limit: 50 }),
  });

  // Collapsed state - just show a thin bar with expand button
  if (isCollapsed) {
    return (
      <aside className="w-12 bg-gray-50 border-r border-gray-200 flex flex-col shrink-0">
        <button
          onClick={() => setIsCollapsed(false)}
          className="h-12 flex items-center justify-center hover:bg-gray-100 transition-colors"
          title="Expand Sources"
        >
          <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 5l7 7-7 7M5 5l7 7-7 7" />
          </svg>
        </button>
        <div className="flex-1 flex items-center justify-center">
          <span className="text-xs text-gray-400 transform -rotate-90 whitespace-nowrap">Sources</span>
        </div>
      </aside>
    );
  }

  return (
    <aside className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col shrink-0">
      <div className="p-4 border-b border-gray-200 flex justify-between items-center bg-white">
        <h2 className="font-semibold text-sm uppercase tracking-wider text-gray-500">Sources</h2>
        <div className="flex items-center gap-1">
          <button className="p-1 hover:bg-gray-100 rounded text-helios-teal" title="Add Source">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
            </svg>
          </button>
          <button
            onClick={() => setIsCollapsed(true)}
            className="p-1 hover:bg-gray-100 rounded text-gray-400 hover:text-gray-600"
            title="Collapse Panel"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M11 19l-7-7 7-7m8 14l-7-7 7-7" />
            </svg>
          </button>
        </div>
      </div>
      
      <div className="p-2 border-b border-gray-200 bg-white">
        <input
          type="text"
          placeholder="Filter sources..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-1 focus:ring-helios-teal focus:border-helios-teal"
        />
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading ? (
          <div className="text-center py-4 text-gray-500 text-sm">Loading...</div>
        ) : texts?.data?.map((text: Text) => {
          const isActive = text.urn === urn;
          return (
            <div 
              key={text.id}
              onClick={() => navigate(`/text/${encodeURIComponent(text.urn)}`)}
              className={`p-3 rounded-lg cursor-pointer group transition-all ${
                isActive 
                  ? 'bg-helios-teal/10 border border-helios-teal/20' 
                  : 'hover:bg-white hover:shadow-sm border border-transparent hover:border-gray-200'
              }`}
            >
              <div className="flex items-start justify-between mb-1">
                <span className={`font-medium text-sm ${isActive ? 'text-helios-teal' : 'text-gray-700'}`}>
                  {text.title}
                </span>
                {isActive && (
                  <span className="text-xs text-helios-teal bg-helios-teal/10 px-1.5 py-0.5 rounded">Active</span>
                )}
              </div>
              <p className={`text-xs truncate ${isActive ? 'text-helios-teal/70' : 'text-gray-500'}`}>
                {text.author}
              </p>
            </div>
          );
        })}

        {/* Upload Box Placeholder */}
        <div className="mt-4 border-2 border-dashed border-gray-300 rounded-lg p-4 text-center hover:border-helios-teal hover:bg-helios-teal/5 cursor-pointer transition-colors">
          <svg className="w-6 h-6 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <span className="text-xs text-gray-600 font-medium">Upload Source</span>
        </div>
      </div>
    </aside>
  );
}
