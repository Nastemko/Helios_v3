import { useState } from 'react';

interface Props {
  isActive: boolean;
  onToggle: () => void;
  isLoading?: boolean;
  disabled?: boolean;
}

export default function TranslationAssistToggle({
  isActive,
  onToggle,
  isLoading = false,
  disabled = false,
}: Props) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div className="relative">
      <button
        onClick={onToggle}
        disabled={disabled || isLoading}
        onMouseEnter={() => setShowTooltip(true)}
        onMouseLeave={() => setShowTooltip(false)}
        className={`
          flex items-center justify-center w-9 h-9 rounded-lg transition-all duration-200
          ${isActive
            ? 'bg-gradient-to-br from-helios-teal to-helios-teal-dark text-white shadow-md shadow-helios-teal/30'
            : 'bg-gray-100 text-gray-500 hover:bg-gray-200 hover:text-gray-700'
          }
          ${disabled ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
          ${isLoading ? 'animate-pulse' : ''}
        `}
        aria-label={isActive ? 'Disable Translation Assist' : 'Enable Translation Assist'}
        title={isActive ? 'Translation Assist Active - Select text to translate' : 'Enable Translation Assist'}
      >
        {isLoading ? (
          <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
        ) : (
          <svg
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            {/* AI/Sparkles icon */}
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={isActive ? 2.5 : 2}
              d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z"
            />
          </svg>
        )}
      </button>

      {/* Tooltip */}
      {showTooltip && !isLoading && (
        <div className="absolute top-full left-1/2 -translate-x-1/2 mt-2 px-3 py-1.5 bg-gray-900 text-white text-xs rounded-lg whitespace-nowrap z-50 shadow-lg">
          {isActive ? (
            <span>Select Greek text to translate</span>
          ) : (
            <span>Enable AI Translation</span>
          )}
          <div className="absolute -top-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-gray-900 rotate-45" />
        </div>
      )}
    </div>
  );
}

