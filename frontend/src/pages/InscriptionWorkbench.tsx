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

type Language = 'greek' | 'latin';

export default function InscriptionWorkbench() {
  // Input state
  const [inputText, setInputText] = useState('');
  const [temperature, setTemperature] = useState(1.0);
  const [language, setLanguage] = useState<Language>('greek');
  
  // Results state
  const [restorationResult, setRestorationResult] = useState<RestorationResult | null>(null);
  const [attributionResult, setAttributionResult] = useState<AttributionResult | null>(null);
  const [contextualizationResult, setContextualizationResult] = useState<ContextualizationResult | null>(null);
  
  // Loading states
  const [isProcessing, setIsProcessing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Browser panel state
  const [showBrowser, setShowBrowser] = useState(true);

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
  const models = modelStatus?.data?.models;
  const greekAvailable = models?.greek?.available ?? false;
  const latinAvailable = models?.latin?.available ?? false;
  const currentModelAvailable = language === 'greek' ? greekAvailable : latinAvailable;

  // Handle "Contextualise" only
  const handleContextualize = useCallback(async () => {
    if (!inputText.trim()) return;
    
    setIsProcessing(true);
    setError(null);
    
    try {
      const ctxRes = await inscriptionApi.contextualize(inputText, language);
      setContextualizationResult(ctxRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'An error occurred');
    } finally {
      setIsProcessing(false);
    }
  }, [inputText, language]);

  // Handle "Attribute" only
  const handleAttribute = useCallback(async () => {
    if (!inputText.trim()) return;
    
    setIsProcessing(true);
    setError(null);
    
    try {
      const attrRes = await inscriptionApi.attribute(inputText, language);
      setAttributionResult(attrRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'An error occurred');
    } finally {
      setIsProcessing(false);
    }
  }, [inputText, language]);

  // Handle "Restore" only
  const handleRestore = useCallback(async () => {
    if (!inputText.trim()) return;
    
    setIsProcessing(true);
    setError(null);
    
    try {
      const restoreRes = await inscriptionApi.restore(inputText, language, temperature);
      setRestorationResult(restoreRes.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || err.message || 'An error occurred');
    } finally {
      setIsProcessing(false);
    }
  }, [inputText, language, temperature]);

  // Load inscription into input
  const handleLoadInscription = useCallback((inscription: InscriptionListItem) => {
    // Fetch full inscription text by text ID
    inscriptionApi.get(inscription.id).then((res) => {
      setInputText(res.data.text);
      setShowBrowser(false);
    }).catch(() => {
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
                Restore ancient text sequences of unknown length, and predict the date 
                and geographic origin of inscriptions using AI models.
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

        {/* Language Toggle */}
        <div className="bg-white rounded-xl p-4 mb-6 shadow-sm border border-stone-200">
          <div className="flex items-center justify-between">
            <div>
              <label className="text-sm font-medium text-stone-700">Language Model</label>
              <p className="text-xs text-stone-500 mt-0.5">
                Select the language for inscription analysis
              </p>
            </div>
            <div className="flex bg-stone-100 rounded-lg p-1">
              <button
                onClick={() => setLanguage('greek')}
                className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
                  language === 'greek'
                    ? 'bg-white text-helios-teal shadow-sm'
                    : 'text-stone-600 hover:text-stone-800'
                }`}
              >
                <span className="flex items-center gap-2">
                  Greek (Ithaca)
                  {greekAvailable ? (
                    <span className="w-2 h-2 bg-green-500 rounded-full" title="Model loaded" />
                  ) : (
                    <span className="w-2 h-2 bg-stone-300 rounded-full" title="Model not loaded" />
                  )}
                </span>
              </button>
              <button
                onClick={() => setLanguage('latin')}
                className={`px-4 py-2 text-sm font-medium rounded-md transition-all ${
                  language === 'latin'
                    ? 'bg-white text-helios-teal shadow-sm'
                    : 'text-stone-600 hover:text-stone-800'
                }`}
              >
                <span className="flex items-center gap-2">
                  Latin (Aeneas)
                  {latinAvailable ? (
                    <span className="w-2 h-2 bg-green-500 rounded-full" title="Model loaded" />
                  ) : (
                    <span className="w-2 h-2 bg-stone-300 rounded-full" title="Model not loaded" />
                  )}
                </span>
              </button>
            </div>
          </div>
        </div>

        {/* Model Status Warning */}
        {!currentModelAvailable && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 mb-6 flex items-start gap-3">
            <svg className="w-5 h-5 text-amber-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <div>
              <p className="text-amber-800 font-medium">
                {language === 'greek' ? 'Greek (Ithaca)' : 'Latin (Aeneas)'} Model Not Loaded
              </p>
              <p className="text-amber-700 text-sm mt-1">
                The {language} model is not currently available. 
                {language === 'latin' && latinAvailable === false && greekAvailable && (
                  <> Try switching to Greek, or </>
                )}
                Check with your administrator about model availability.
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
          onContextualize={handleContextualize}
          onAttribute={handleAttribute}
          onRestore={handleRestore}
          onClear={handleClear}
          isProcessing={isProcessing}
          modelAvailable={currentModelAvailable}
          language={language}
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
