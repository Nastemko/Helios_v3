import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import { textApi } from "../services/api";
import type { Text } from "../types";

const PAGE_SIZE = 30;

export default function SourcesSidebar() {
  const { textId } = useParams<{ textId: string }>();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [isCollapsed, setIsCollapsed] = useState(!!textId);
  const containerRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } =
    useInfiniteQuery({
      queryKey: ["texts-sidebar", search],
      queryFn: ({ pageParam = 0 }) =>
        textApi.list({ search, skip: pageParam, limit: PAGE_SIZE }),
      initialPageParam: 0,
      getNextPageParam: (lastPage, _allPages, lastPageParam) => {
        if (!lastPage.data || lastPage.data.length < PAGE_SIZE)
          return undefined;
        return lastPageParam + PAGE_SIZE;
      },
    });

  const texts = data?.pages.flatMap((page) => page.data) ?? [];

  // IntersectionObserver to trigger loading the next page.
  // Important: include texts.length in the dependency array so the effect
  // re-runs when new items render and the sentinel may be attached to the DOM.
  useEffect(() => {
    const container = containerRef.current;
    const sentinel = sentinelRef.current;
    if (!container || !sentinel) return;

    // If there is no next page, no need to observe.
    if (!hasNextPage) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const [entry] = entries;
        if (entry.isIntersecting && hasNextPage && !isFetchingNextPage) {
          fetchNextPage();
        }
      },
      {
        root: container,
        rootMargin: "200px",
      },
    );
    observer.observe(sentinel);

    return () => observer.disconnect();
    // texts.length ensures the observer is (re)created when the list grows/shrinks.
    // isCollapsed ensures the observer is created when the sidebar expands
    // (refs are null while collapsed, so the effect must re-run after expanding).
  }, [
    hasNextPage,
    isFetchingNextPage,
    fetchNextPage,
    texts.length,
    isCollapsed,
  ]);

  // Collapsed state - just show a thin bar with expand button
  if (isCollapsed) {
    return (
      <aside className="w-12 bg-gray-50 border-r border-gray-200 flex flex-col shrink-0 h-full min-h-0">
        <button
          onClick={() => setIsCollapsed(false)}
          className="h-12 flex items-center justify-center hover:bg-gray-100 transition-colors"
          title="Expand Sources"
        >
          <svg
            className="w-5 h-5 text-gray-500"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M13 5l7 7-7 7M5 5l7 7-7 7"
            />
          </svg>
        </button>
        <div className="flex-1 flex items-center justify-center">
          <span className="text-xs text-gray-400 transform -rotate-90 whitespace-nowrap">
            Sources
          </span>
        </div>
      </aside>
    );
  }

  return (
    <aside className="w-64 bg-gray-50 border-r border-gray-200 flex flex-col shrink-0 h-full min-h-0">
      <div className="p-4 border-b border-gray-200 flex justify-between items-center bg-white">
        <h2 className="font-semibold text-sm uppercase tracking-wider text-gray-500">
          Sources
        </h2>
        <button
          onClick={() => setIsCollapsed(true)}
          className="p-1 hover:bg-gray-100 rounded text-gray-400 hover:text-gray-600"
          title="Collapse Panel"
        >
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M13 5l7 7-7 7M5 5l7 7-7 7"
            />
          </svg>
        </button>
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

      <div ref={containerRef} className="flex-1 overflow-y-auto p-2 space-y-1">
        {isLoading ? (
          <div className="text-center py-4 text-gray-500 text-sm">
            Loading...
          </div>
        ) : (
          texts.map((text: Text) => {
            const isActive = text.id.toString() === textId;
            return (
              <div
                key={text.id}
                onClick={() => navigate(`/text/${text.id}`)}
                className={`p-3 rounded-lg cursor-pointer group transition-all ${
                  isActive
                    ? "bg-helios-teal/10 border border-helios-teal/20"
                    : "hover:bg-white hover:shadow-sm border border-transparent hover:border-gray-200"
                }`}
              >
                <div className="flex items-start justify-between mb-1">
                  <span
                    className={`font-medium text-sm ${isActive ? "text-helios-teal" : "text-gray-700"}`}
                  >
                    {text.title}
                  </span>
                  {isActive && (
                    <span className="text-xs text-helios-teal bg-helios-teal/10 px-1.5 py-0.5 rounded">
                      Active
                    </span>
                  )}
                </div>
                <p
                  className={`text-xs truncate ${isActive ? "text-helios-teal/70" : "text-gray-500"}`}
                >
                  {text.author}
                </p>
              </div>
            );
          })
        )}

        {/* Sentinel for infinite scroll */}
        <div ref={sentinelRef} className="h-1" />

        {isFetchingNextPage && (
          <div className="text-center py-3 text-gray-400 text-xs">
            Loading more...
          </div>
        )}
      </div>
    </aside>
  );
}
