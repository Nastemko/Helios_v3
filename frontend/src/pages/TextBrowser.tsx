import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { textApi } from '../services/api';
import type { Text } from '../types';

export default function TextBrowser() {
  const [search, setSearch] = useState('');
  const [language, setLanguage] = useState<string>('');
  
  const { data: texts, isLoading } = useQuery({
    queryKey: ['texts', search, language],
    queryFn: () => textApi.list({ search, language, limit: 100 }),
  });

  return (
    <div className="max-w-7xl mx-auto px-4 py-8">
      <h1 className="text-4xl font-bold mb-8">Browse Classical Texts</h1>
      
      {/* Filters */}
      <div className="bg-white p-6 rounded-lg shadow-sm border mb-8">
        <div className="flex flex-col md:flex-row gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Search by author or title
            </label>
            <input
              type="text"
              placeholder="e.g., Homer, Iliad..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          
          <div className="w-full md:w-48">
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Language
            </label>
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value)}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            >
              <option value="">All Languages</option>
              <option value="grc">Greek</option>
              <option value="lat">Latin</option>
            </select>
          </div>
        </div>
      </div>

      {/* Results */}
      {isLoading ? (
        <div className="text-center py-12">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-4 border-blue-600 border-t-transparent"></div>
          <p className="mt-4 text-gray-600">Loading texts...</p>
        </div>
      ) : texts?.data && texts.data.length > 0 ? (
        <div className="grid gap-4">
          {texts.data.map((text: Text) => (
            <Link
              key={text.id}
              to={`/text/${encodeURIComponent(text.urn)}`}
              className="block bg-white p-6 rounded-lg shadow-sm border hover:border-blue-300 hover:shadow-md transition"
            >
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <div className="flex items-center gap-3 mb-2">
                    <h3 className="text-xl font-semibold text-gray-900">
                      {text.title}
                    </h3>
                    {text.is_fragment && (
                      <span className="px-2 py-1 text-xs bg-yellow-100 text-yellow-800 rounded-full">
                        Fragment
                      </span>
                    )}
                    <span className="px-2 py-1 text-xs bg-gray-100 text-gray-700 rounded-full uppercase">
                      {text.language}
                    </span>
                  </div>
                  <p className="text-gray-600 font-medium mb-1">{text.author}</p>
                  <p className="text-sm text-gray-500">{text.urn}</p>
                </div>
                
                <div className="text-blue-600 ml-4">
                  <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                  </svg>
                </div>
              </div>
            </Link>
          ))}
        </div>
      ) : (
        <div className="text-center py-12 bg-white rounded-lg border">
          <p className="text-gray-600">No texts found matching your criteria</p>
        </div>
      )}
    </div>
  );
}

