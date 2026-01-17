import { useState, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { inscriptionApi } from '../services/api';
import InscriptionInput from '../components/inscription/InscriptionInput';
import ResultsPanel from '../components/inscription/ResultsPanel';
import InscriptionBrowser from '../components/inscription/InscriptionBrowser';
import type {
  RestorationResult,
  AttributionResult,
  ContextualizationResult,
  InscriptionListItem,
} from '../types';

export default function InscriptionWorkbench() {
  // Input state
  const [inputText, setInputText] = useState('');
  const [temperature, setTemperature] = useState(1.0);
  
  // Results state
  const [restorationResult, setRestorationResult] = useState<RestorationResult | null>(null);
  const [attributionResult, setAttributionResult] = useState<AttributionResult | null>(null);
  const [contextualizationResult, setContextualizationResult] = useState<ContextualizationResult | null>(null);
  
  // Loading states
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Browser panel state
  const [showBrowser, setShowBrowser] = useState(false);

  // Fetch model status
  const { data: modelStatus } = useQuery({
    queryKey: ['ithaca-model-status'],
    queryFn: () => inscriptionApi.getModelStatus(),
    staleTime: 60000, // Cache for 1 minute
  });

  // Fetch corpus stats
  const { data: statsData } = useQuery({
    queryKey: ['inscription-stats'],
    queryFn: () => inscriptionApi.getStats(),
    staleTime: 300000, // Cache for 5 minutes
  });

  const stats = statsData?.data;
  const modelAvailable = modelStatus?.data?.available ?? false;

  // Handle "Contextualise and Attribute" (no restoration)
  const handleAttributeOnly = useCallback(async () => {
    if (!inputText.trim()) return;
    
    setIsProcessing(true);
    setError(null);
    setRestorationResult(null);
    
    try {
      const [attrRes, ctxRes] = await Promise.all([
        inscriptionApi.attribute(inputText),
        inscriptionApi.contextualize(inputText),
      ]);
      
      setAttributionResult(attrRes.data);
      setContextualizationResult(ctxRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'An error occurred');
    } finally {
      setIsProcessing(false);
    }
  }, [inputText]);

  // Handle "Contextualise, Restore and Attribute" (full analysis)
  const handleFullAnalysis = useCallback(async () => {
    if (!inputText.trim()) return;
    
    setIsProcessing(true);
    setError(null);
    
    try {
      const [restoreRes, attrRes, ctxRes] = await Promise.all([
        inscriptionApi.restore(inputText, temperature),
        inscriptionApi.attribute(inputText),
        inscriptionApi.contextualize(inputText),
      ]);
      
      setRestorationResult(restoreRes.data);
      setAttributionResult(attrRes.data);
      setContextualizationResult(ctxRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'An error occurred');
    } finally {
      setIsProcessing(false);
    }
  }, [inputText, temperature]);

  // Load inscription into input
  const handleLoadInscription = useCallback((inscription: InscriptionListItem) => {
    // Fetch full inscription text
    inscriptionApi.get(inscription.phi_id).then((res) => {
      setInputText(res.data.text);
      setShowBrowser(false);
    }).catch((err) => {
      setError('Failed to load inscription');
    });
  }, []);

  // Clear results
  const handleClear = useCallback(() => {
    setInputText('');
    setRestorationResult(null);
    setAttributionResult(null);
    setContextualizationResult(null);
    setError(null);
  }, []);

  const hasResults = restorationResult || attributionResult || contextualizationResult;

  return (
    <div className="flex-1 overflow-y-auto bg-gradient-to-b from-stone-100 to-stone-200">
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* Header Banner */}
        <div className="bg-gradient-to-r from-helios-teal to-teal-700 rounded-xl p-6 mb-8 text-white shadow-lg">
          <div className="flex items-start justify-between">
            <div>
              <div className="inline-block bg-amber-400 text-amber-900 text-xs font-bold px-2 py-0.5 rounded mb-3">
                BETA
              </div>
              <h1 className="text-2xl font-bold mb-2">Inscription Workbench</h1>
              <p className="text-white/90 text-sm max-w-xl">
                Restore ancient Greek text sequences of unknown length, and predict the date 
                and geographic origin of inscriptions using the Ithaca model.
              </p>
            </div>
            {stats && (
              <div className="text-right text-sm text-white/80">
                <div className="font-semibold text-white">{stats.total_inscriptions.toLocaleString()}</div>
                <div>inscriptions in corpus</div>
              </div>
            )}
          </div>
        </div>

        {/* Model Status Warning */}
        {!modelAvailable && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6 flex items-start gap-3">
            <svg className="w-5 h-5 text-amber-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <p className="text-amber-800 font-medium">Model Integration Coming Soon</p>
              <p className="text-amber-700 text-sm mt-1">
                The Ithaca restoration and attribution model is being integrated. 
                You can browse and search the inscription corpus while we complete the setup.
              </p>
            </div>
          </div>
        )}

        {/* Input Section */}
        <InscriptionInput
          value={inputText}
          onChange={setInputText}
          temperature={temperature}
          onTemperatureChange={setTemperature}
          onAttributeOnly={handleAttributeOnly}
          onFullAnalysis={handleFullAnalysis}
          onClear={handleClear}
          isProcessing={isProcessing}
          modelAvailable={modelAvailable}
        />

        {/* Error Display */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 mb-6 flex items-start gap-3">
            <svg className="w-5 h-5 text-red-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div>
              <p className="text-red-800 font-medium">Error</p>
              <p className="text-red-700 text-sm mt-1">{error}</p>
            </div>
          </div>
        )}

        {/* Results Section */}
        {hasResults && (
          <ResultsPanel
            restoration={restorationResult}
            attribution={attributionResult}
            contextualization={contextualizationResult}
            onLoadSimilar={(text) => setInputText(text)}
          />
        )}

        {/* Browse Inscriptions Panel */}
        <div className="mt-8">
          <button
            onClick={() => setShowBrowser(!showBrowser)}
            className="flex items-center gap-2 text-stone-600 hover:text-stone-800 font-medium transition-colors"
          >
            <svg 
              className={`w-5 h-5 transition-transform ${showBrowser ? 'rotate-90' : ''}`} 
              fill="none" 
              stroke="currentColor" 
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            Browse Inscription Corpus
          </button>
          
          {showBrowser && (
            <div className="mt-4">
              <InscriptionBrowser onSelectInscription={handleLoadInscription} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

