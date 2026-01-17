import { useMemo } from 'react';
import type {
  RestorationResult,
  AttributionResult,
  ContextualizationResult,
} from '../../types';

interface ResultsPanelProps {
  restoration: RestorationResult | null;
  attribution: AttributionResult | null;
  contextualization: ContextualizationResult | null;
  onLoadSimilar: (text: string) => void;
}

export default function ResultsPanel({
  restoration,
  attribution,
  contextualization,
  onLoadSimilar,
}: ResultsPanelProps) {
  // Format year for display (negative = BC, positive = AD)
  const formatYear = (year: number | null): string => {
    if (year === null) return '?';
    if (year < 0) return `${Math.abs(year)} BC`;
    if (year > 0) return `${year} AD`;
    return '1 BC/AD';
  };

  // Get date range display
  const dateRangeDisplay = useMemo(() => {
    if (!attribution?.predicted_date_range) return null;
    const { min, max, confidence } = attribution.predicted_date_range;
    if (min === null && max === null) return null;
    
    const minStr = formatYear(min);
    const maxStr = formatYear(max);
    const confPct = Math.round((confidence || 0) * 100);
    
    if (min === max) {
      return { range: minStr, confidence: confPct };
    }
    return { range: `${minStr} – ${maxStr}`, confidence: confPct };
  }, [attribution]);

  // Get top locations
  const topLocations = useMemo(() => {
    if (!attribution?.locations) return [];
    return attribution.locations
      .filter(loc => loc.score > 0.01)
      .slice(0, 5);
  }, [attribution]);

  // Render restored text with highlights
  const renderRestoredText = () => {
    if (!restoration?.top_prediction) return null;
    
    const text = restoration.top_prediction;
    const restored = new Set(restoration.restored_indices || []);
    
    return (
      <div className="font-serif text-xl leading-relaxed">
        {text.split('').map((char, idx) => (
          <span
            key={idx}
            className={restored.has(idx) 
              ? 'bg-teal-200 text-teal-900 px-0.5 rounded' 
              : ''
            }
          >
            {char}
          </span>
        ))}
      </div>
    );
  };

  // Check if we have any real results
  const hasModelResults = attribution?.available || restoration?.available || contextualization?.available;

  return (
    <div className="space-y-6">
      {/* Restoration Result */}
      {restoration && (
        <div className="bg-white rounded-xl shadow-sm border border-stone-200 p-6">
          <h3 className="text-lg font-semibold text-stone-800 mb-4 flex items-center gap-2">
            <svg className="w-5 h-5 text-teal-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
            </svg>
            Restored Text
          </h3>
          
          {restoration.available ? (
            <>
              {renderRestoredText()}
              
              {restoration.alternatives && restoration.alternatives.length > 1 && (
                <div className="mt-4">
                  <details className="group">
                    <summary className="cursor-pointer text-sm text-stone-600 hover:text-stone-800">
                      View alternative restorations ({restoration.alternatives.length})
                    </summary>
                    <div className="mt-2 space-y-2 pl-4 border-l-2 border-stone-200">
                      {restoration.alternatives.slice(0, 5).map((alt, idx) => (
                        <div key={idx} className="text-sm">
                          <span className="font-serif">{alt.text}</span>
                          <span className="ml-2 text-stone-400">
                            ({Math.round(alt.score * 100)}%)
                          </span>
                        </div>
                      ))}
                    </div>
                  </details>
                </div>
              )}
            </>
          ) : (
            <div className="text-stone-500 italic">
              {restoration.message || 'Restoration model not available'}
            </div>
          )}
        </div>
      )}

      {/* Attribution Results */}
      {attribution && (
        <div className="bg-white rounded-xl shadow-sm border border-stone-200 p-6">
          <h3 className="text-lg font-semibold text-stone-800 mb-4 flex items-center gap-2">
            <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
            </svg>
            Attribution
          </h3>

          {attribution.available ? (
            <div className="grid md:grid-cols-2 gap-6">
              {/* Date Prediction */}
              <div>
                <h4 className="text-sm font-medium text-stone-600 mb-3">Predicted Date</h4>
                {dateRangeDisplay ? (
                  <div className="flex items-baseline gap-2">
                    <span className="text-2xl font-bold text-stone-800">
                      {dateRangeDisplay.range}
                    </span>
                    <span className="text-sm text-stone-500">
                      ({dateRangeDisplay.confidence}% confidence)
                    </span>
                  </div>
                ) : (
                  <div className="text-stone-500">Unable to determine date</div>
                )}
                
                {/* Mini date distribution chart */}
                {attribution.year_scores && attribution.year_scores.some(s => s > 0) && (
                  <div className="mt-4 h-16 flex items-end gap-px">
                    {attribution.year_scores.map((score, idx) => {
                      const maxScore = Math.max(...attribution.year_scores);
                      const height = maxScore > 0 ? (score / maxScore) * 100 : 0;
                      return (
                        <div
                          key={idx}
                          className="flex-1 bg-amber-400 rounded-t-sm min-w-[2px]"
                          style={{ height: `${height}%` }}
                          title={`${-800 + idx * 10}: ${Math.round(score * 100)}%`}
                        />
                      );
                    })}
                  </div>
                )}
                <div className="flex justify-between text-xs text-stone-400 mt-1">
                  <span>800 BC</span>
                  <span>1 BC/AD</span>
                  <span>800 AD</span>
                </div>
              </div>

              {/* Location Prediction */}
              <div>
                <h4 className="text-sm font-medium text-stone-600 mb-3">Predicted Location</h4>
                {topLocations.length > 0 ? (
                  <div className="space-y-2">
                    {topLocations.map((loc, idx) => (
                      <div key={idx} className="flex items-center gap-2">
                        <div className="flex-1">
                          <div className="flex items-center justify-between text-sm">
                            <span className={idx === 0 ? 'font-medium text-stone-800' : 'text-stone-600'}>
                              {loc.name || `Region ${loc.location_id}`}
                            </span>
                            <span className="text-stone-500">
                              {Math.round(loc.score * 100)}%
                            </span>
                          </div>
                          <div className="mt-1 h-2 bg-stone-100 rounded-full overflow-hidden">
                            <div 
                              className="h-full bg-teal-500 rounded-full"
                              style={{ width: `${loc.score * 100}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-stone-500">Unable to determine location</div>
                )}
              </div>
            </div>
          ) : (
            <div className="text-stone-500 italic">
              {attribution.message || 'Attribution model not available'}
            </div>
          )}
        </div>
      )}

      {/* Similar Inscriptions */}
      {contextualization && (
        <div className="bg-white rounded-xl shadow-sm border border-stone-200 p-6">
          <h3 className="text-lg font-semibold text-stone-800 mb-4 flex items-center gap-2">
            <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
            </svg>
            Similar Inscriptions
          </h3>

          {contextualization.available && contextualization.similar.length > 0 ? (
            <div className="space-y-3">
              {contextualization.similar.slice(0, 10).map((insc, idx) => (
                <div 
                  key={idx}
                  className="p-3 bg-stone-50 rounded-lg hover:bg-stone-100 transition-colors"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 text-sm text-stone-600 mb-1">
                        <span className="font-medium">PHI {insc.phi_id}</span>
                        {insc.region && (
                          <>
                            <span className="text-stone-300">•</span>
                            <span>{insc.region}</span>
                          </>
                        )}
                        {(insc.date_min || insc.date_max) && (
                          <>
                            <span className="text-stone-300">•</span>
                            <span>
                              {formatYear(insc.date_min)}
                              {insc.date_max !== insc.date_min && ` – ${formatYear(insc.date_max)}`}
                            </span>
                          </>
                        )}
                      </div>
                      <p className="text-sm font-serif text-stone-700 truncate">
                        {insc.text}
                      </p>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-xs text-stone-500">
                        {Math.round(insc.score * 100)}% match
                      </span>
                      <button
                        onClick={() => onLoadSimilar(insc.text)}
                        className="p-1.5 text-stone-400 hover:text-teal-600 hover:bg-teal-50 rounded transition-colors"
                        title="Load into workbench"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="text-stone-500 italic">
              {contextualization.message || 'No similar inscriptions found'}
            </div>
          )}
        </div>
      )}

      {/* Placeholder notice when model not available */}
      {!hasModelResults && (
        <div className="bg-stone-50 border border-stone-200 rounded-lg p-4 text-center text-stone-600">
          <p className="font-medium">Results Preview</p>
          <p className="text-sm mt-1">
            The Ithaca model is being integrated. These are placeholder results.
          </p>
        </div>
      )}
    </div>
  );
}

