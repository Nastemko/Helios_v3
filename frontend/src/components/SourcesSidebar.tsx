import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate, useParams } from 'react-router-dom';
import { textApi } from '../services/api';
import type { Text } from '../types';

export default function SourcesSidebar() {
  const { urn } = useParams<{ urn: string }>();
  const navigate = useNavigate();
  const [search, setSearch] = useState('');

  const { data: texts, isLoading } = useQuery({
    queryKey: ['texts', search],
    queryFn: () => textApi.list({ search, limit: 50 }),
  });

  return (
    <aside className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col shrink-0">
      <div className="p-4 border-b border-gray-200 flex justify-between items-center bg-white">
        <h2 className="font-semibold text-sm uppercase tracking-wider text-gray-500">Sources</h2>
        <button className="p-1 hover:bg-gray-100 rounded text-blue-600">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4"></path></svg>
        </button>
      </div>
      
      <div className="p-2 border-b border-gray-200 bg-white">
        <input
            type="text"
            placeholder="Filter sources..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-md focus:ring-1 focus:ring-blue-500 focus:border-blue-500"
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
                        ? 'bg-blue-50 border border-blue-100' 
                        : 'hover:bg-white hover:shadow-sm border border-transparent hover:border-gray-200'
                    }`}
                >
                    <div className="flex items-start justify-between mb-1">
                        <span className={`font-medium text-sm ${isActive ? 'text-blue-900' : 'text-gray-700'}`}>
                            {text.title}
                        </span>
                        {isActive && (
                            <span className="text-xs text-blue-600 bg-blue-100 px-1.5 py-0.5 rounded">Active</span>
                        )}
                    </div>
                    <p className={`text-xs truncate ${isActive ? 'text-blue-700' : 'text-gray-500'}`}>
                        {text.author}
                    </p>
                </div>
            );
        })}

        {/* Upload Box Placeholder */}
         <div className="mt-4 border-2 border-dashed border-gray-300 rounded-lg p-4 text-center hover:border-blue-400 hover:bg-blue-50 cursor-pointer transition-colors">
            <svg className="w-6 h-6 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"></path></svg>
            <span className="text-xs text-gray-600 font-medium">Upload Source</span>
        </div>
      </div>
    </aside>
  );
}

