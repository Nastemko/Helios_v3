import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { textApi } from "../services/api";
import type { Text } from "../types";
import { useCallback, useEffect, useRef, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { textApi } from "../services/api";
import type { Text } from "../types";

const PAGE_SIZE = 30;

export default function TextBrowser() {
  const [search, setSearch] = useState("");
  const [language, setLanguage] = useState<string>("");
  const sentinelRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } =
    useInfiniteQuery({
      queryKey: ["texts", search, language],
      queryFn: ({ pageParam = 0 }) =>
        textApi.list({ search, language, skip: pageParam, limit: PAGE_SIZE }),
      initialPageParam: 0,
      getNextPageParam: (lastPage, _allPages, lastPageParam) => {
        // If we got fewer items than PAGE_SIZE, there are no more pages
        if (!lastPage.data || lastPage.data.length < PAGE_SIZE)
          return undefined;
        return lastPageParam + PAGE_SIZE;
      },
    });

  const texts = data?.pages.flatMap((page) => page.data) ?? [];

  // IntersectionObserver to trigger loading the next page
  const handleObserver = useCallback(
    (entries: IntersectionObserverEntry[]) => {
      const [entry] = entries;
      if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
        fetchNextPage();
      }
    },
    [hasNextPage, isFetchingNextPage, fetchNextPage],
  );

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;

    const observer = new IntersectionObserver(handleObserver, {
      rootMargin: "200px",
    });
    observer.observe(sentinel);

    return () => observer.disconnect();
  }, [handleObserver]);

  return (
    <div className="flex-1 overflow-y-auto bg-gray-50">
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
        ) : texts.length > 0 ? (
          <div className="grid gap-4">
            {texts.map((text: Text) => (
              <Link
                key={text.id}
                to={`/text/${text.id}`}
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
                    <p className="text-gray-600 font-medium mb-1">
                      {text.author}
                    </p>
                    <p className="text-sm text-gray-500">{text.local_id}</p>
                  </div>

                  <div className="text-blue-600 ml-4">
                    <svg
                      className="w-6 h-6"
                      fill="none"
                      stroke="currentColor"
                      viewBox="0 0 24 24"
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                      />
                    </svg>
                  </div>
                </div>
              </Link>
            ))}

            {/* Sentinel for infinite scroll */}
            <div ref={sentinelRef} className="h-1" />

            {isFetchingNextPage && (
              <div className="text-center py-6">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-4 border-blue-600 border-t-transparent"></div>
                <p className="mt-2 text-gray-500 text-sm">
                  Loading more texts...
                </p>
              </div>
            )}

            {!hasNextPage && texts.length > PAGE_SIZE && (
              <p className="text-center text-gray-400 text-sm py-4">
                All texts loaded
              </p>
            )}
          </div>
        ) : (
          <div className="text-center py-12 bg-white rounded-lg border">
            <p className="text-gray-600">
              No texts found matching your criteria
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
