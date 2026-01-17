import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { inscriptionApi } from '../../services/api';
import type { InscriptionListItem, RegionCount } from '../../types';

interface InscriptionBrowserProps {
  onSelectInscription: (inscription: InscriptionListItem) => void;
}

export default function InscriptionBrowser({ onSelectInscription }: InscriptionBrowserProps) {
  const [search, setSearch] = useState('');
  const [regionMain, setRegionMain] = useState('');
  const [dateMin, setDateMin] = useState<string>('');
  const [dateMax, setDateMax] = useState<string>('');
  const [page, setPage] = useState(0);
  const limit = 20;

  // Fetch regions for dropdown
  const { data: regionsData } = useQuery({
    queryKey: ['inscription-regions'],
    queryFn: () => inscriptionApi.getRegions('main'),
    staleTime: 300000, // Cache for 5 minutes
  });

  const regions = regionsData?.data || [];

  // Build query params
  const queryParams = {
    search: search || undefined,
    region_main: regionMain || undefined,
    date_min: dateMin ? parseInt(dateMin) : undefined,
    date_max: dateMax ? parseInt(dateMax) : undefined,
    skip: page * limit,
    limit,
  };

  // Fetch inscriptions
  const { data: inscriptionsData, isLoading, isFetching } = useQuery({
    queryKey: ['inscriptions', queryParams],
    queryFn: () => inscriptionApi.list(queryParams),
    staleTime: 60000, // Cache for 1 minute
  });

  const inscriptions = inscriptionsData?.data || [];

  // Handle search with debounce reset
  const handleSearchChange = useCallback((value: string) => {
    setSearch(value);
    setPage(0);
  }, []);

  // Handle filter changes
  const handleRegionChange = useCallback((value: string) => {
    setRegionMain(value);
    setPage(0);
  }, []);

  const handleDateMinChange = useCallback((value: string) => {
    setDateMin(value);
    setPage(0);
  }, []);

  const handleDateMaxChange = useCallback((value: string) => {
    setDateMax(value);
    setPage(0);
  }, []);

  const handleClearFilters = useCallback(() => {
    setSearch('');
    setRegionMain('');
    setDateMin('');
    setDateMax('');
    setPage(0);
  }, []);

  const hasFilters = search || regionMain || dateMin || dateMax;

  return (
    <div className="bg-white rounded-xl shadow-sm border border-stone-200 overflow-hidden">
      {/* Filters */}
      <div className="p-4 bg-stone-50 border-b border-stone-200">
        <div className="flex flex-wrap items-end gap-4">
          {/* Search */}
          <div className="flex-1 min-w-[200px]">
            <label className="block text-xs font-medium text-stone-600 mb-1">
              Search text content
            </label>
            <input
              type="text"
              value={search}
              onChange={(e) => handleSearchChange(e.target.value)}
              placeholder="e.g., εδοξεν, βουλη..."
              className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:ring-2 focus:ring-helios-teal focus:border-transparent"
            />
          </div>

          {/* Region Filter */}
          <div className="w-48">
            <label className="block text-xs font-medium text-stone-600 mb-1">
              Region
            </label>
            <select
              value={regionMain}
              onChange={(e) => handleRegionChange(e.target.value)}
              className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:ring-2 focus:ring-helios-teal focus:border-transparent bg-white"
            >
              <option value="">All Regions</option>
              {regions.map((region: RegionCount) => (
                <option key={region.region} value={region.region}>
                  {region.region} ({region.count.toLocaleString()})
                </option>
              ))}
            </select>
          </div>

          {/* Date Range */}
          <div className="flex items-end gap-2">
            <div className="w-24">
              <label className="block text-xs font-medium text-stone-600 mb-1">
                Date from
              </label>
              <input
                type="number"
                value={dateMin}
                onChange={(e) => handleDateMinChange(e.target.value)}
                placeholder="-500"
                className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:ring-2 focus:ring-helios-teal focus:border-transparent"
              />
            </div>
            <span className="text-stone-400 pb-2">–</span>
            <div className="w-24">
              <label className="block text-xs font-medium text-stone-600 mb-1">
                Date to
              </label>
              <input
                type="number"
                value={dateMax}
                onChange={(e) => handleDateMaxChange(e.target.value)}
                placeholder="100"
                className="w-full px-3 py-2 border border-stone-300 rounded-lg text-sm focus:ring-2 focus:ring-helios-teal focus:border-transparent"
              />
            </div>
          </div>

          {/* Clear Filters */}
          {hasFilters && (
            <button
              onClick={handleClearFilters}
              className="px-3 py-2 text-sm text-stone-600 hover:text-stone-800 transition-colors"
            >
              Clear filters
            </button>
          )}
        </div>
        
        <p className="text-xs text-stone-500 mt-2">
          Date format: negative values = BC (e.g., -350 = 350 BC), positive = AD
        </p>
      </div>

      {/* Results */}
      <div className="divide-y divide-stone-100">
        {isLoading ? (
          <div className="p-8 text-center">
            <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-helios-teal border-t-transparent"></div>
            <p className="mt-2 text-stone-600">Loading inscriptions...</p>
          </div>
        ) : inscriptions.length === 0 ? (
          <div className="p-8 text-center text-stone-600">
            No inscriptions found matching your criteria
          </div>
        ) : (
          inscriptions.map((inscription: InscriptionListItem) => (
            <div
              key={inscription.id}
              className="p-4 hover:bg-stone-50 transition-colors cursor-pointer"
              onClick={() => onSelectInscription(inscription)}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 text-sm mb-1">
                    <span className="font-medium text-stone-800">
                      PHI {inscription.phi_id}
                    </span>
                    {inscription.region_sub && (
                      <>
                        <span className="text-stone-300">•</span>
                        <span className="text-stone-600">{inscription.region_sub}</span>
                      </>
                    )}
                    {inscription.date_str && (
                      <>
                        <span className="text-stone-300">•</span>
                        <span className="text-stone-500">{inscription.date_str.trim()}</span>
                      </>
                    )}
                  </div>
                  <p className="text-sm font-serif text-stone-700 line-clamp-2">
                    {inscription.text_preview}
                  </p>
                </div>
                <button
                  className="shrink-0 p-2 text-stone-400 hover:text-helios-teal hover:bg-teal-50 rounded-lg transition-colors"
                  title="Load into workbench"
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                  </svg>
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Pagination */}
      {inscriptions.length > 0 && (
        <div className="p-4 bg-stone-50 border-t border-stone-200 flex items-center justify-between">
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0 || isFetching}
            className="px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-200 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Previous
          </button>
          
          <span className="text-sm text-stone-600">
            Page {page + 1}
            {isFetching && <span className="ml-2 text-stone-400">(loading...)</span>}
          </span>
          
          <button
            onClick={() => setPage(page + 1)}
            disabled={inscriptions.length < limit || isFetching}
            className="px-4 py-2 text-sm font-medium text-stone-700 hover:bg-stone-200 rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}

