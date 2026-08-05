import { useState } from 'react';

type Language = 'greek' | 'latin';

interface InscriptionInputProps {
  value: string;
  onChange: (value: string) => void;
  temperature: number;
  onTemperatureChange: (temp: number) => void;
  maxRestorationLen: number;
  onMaxRestorationLenChange: (len: number) => void;
  onContextualize: () => void;
  onAttribute: () => void;
  onRestore: () => void;
  onClear: () => void;
  isProcessing: boolean;
  modelAvailable: boolean;
  language: Language;
}

// Sample inscriptions for the "Show me an example" dropdown
const GREEK_EXAMPLES = [
  {
    name: "Athenian Decree (with gaps)",
    text: "εδοξεν τηι βουληι και τωι δημωι λυσιστρατος ειπε επειδη διοφανης ανηρ αγαθος ων διατελει περι δηλιους δεδοχθαι τωι ????? διοφανην καλλι???????? ??ηναιον προξενον ειναι δ????????? αυτογ και εκγονους κ?? ειναι αυτοις ατελειαν εν δηλωι παντων και γης και οικιας εγκτησιν και προσοδον προς τημ βουλην και τον δημον πρωτοις μετα τα ιερα και τα αλλα οσα και τοις αλλοις προξενοις και ευεργεταις του ιερου δεδοται",
  },
  {
    name: "Funerary Inscription",
    text: "ευψυχι αλεξανδρε ουδεις αθανατος",
  },
  {
    name: "Votive Offering",
    text: "φιλεταιρος ευμενου περγαμευς μουσαις καφισιας εποιησε",
  },
  {
    name: "With Unknown Length Gap (#)",
    text: "βασιλευοντος τολεμαιου του τολεμαιου ετους ενδεκατου μηνος περειτιου εκκλησιας κυριας γενομενης εδοξε # τωι δημωι",
  },
];

const LATIN_EXAMPLES = [
  {
    name: "Military Diploma (with gaps)",
    text: "imp caesar divi # f augustus pontifex maximus tribunicia potestate ????? cos xiii pater patriae",
  },
  {
    name: "Funerary Inscription",
    text: "dis manibus sacrum gaius iulius maximus vixit annis lx mensibus iii diebus x hic situs est sit tibi terra levis",
  },
  {
    name: "Votive Altar",
    text: "iovi optimo maximo sacrum pro salute imperatoris caesaris traiani hadriani augusti",
  },
  {
    name: "Building Inscription (with gap)",
    text: "senatus populusque romanus # restituit",
  },
];

export default function InscriptionInput({
  value,
  onChange,
  temperature,
  onTemperatureChange,
  maxRestorationLen,
  onMaxRestorationLenChange,
  onContextualize,
  onAttribute,
  onRestore,
  onClear,
  isProcessing,
  modelAvailable,
  language,
}: InscriptionInputProps) {
  const [showExamples, setShowExamples] = useState(false);

  // The model rejects anything shorter than MIN_TEXT_LEN=25 after it strips
  // accents and collapses whitespace, so anything below that never reaches it.
  const charCount = value.length;
  const isValidLength = charCount >= 25 && charCount <= 760;
  // '-' is deliberately absent: the API rejects it, so it must not enable Restore.
  const hasGaps = value.includes('?') || value.includes('#');
  // '#' searches over gap length as well as content, so it is far slower than
  // '?'. The control below only matters for these inputs, so only show it then.
  const hasUnknownLengthGap = value.includes('#');

  const examples = language === 'greek' ? GREEK_EXAMPLES : LATIN_EXAMPLES;

  const placeholderText = language === 'greek'
    ? `Enter Greek inscription text here...

Use one ? per missing character (e.g., κα?λος)
????? means exactly five missing characters
Use # when you don't know how many are missing (e.g., εδοξεν # τωι δημωι)`
    : `Enter Latin inscription text here...

Use one ? per missing character (e.g., ma?imus)
????? means exactly five missing characters
Use # when you don't know how many are missing (e.g., imp caesar # augustus)`;
  
  const handleExampleSelect = (text: string) => {
    onChange(text);
    setShowExamples(false);
  };

  return (
    <div className="bg-white rounded-xl shadow-sm border border-stone-200 p-6 mb-6">
      {/* Text Input Area */}
      <div className="relative">
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholderText}
          className="w-full h-48 p-4 border border-stone-300 rounded-lg font-serif text-lg leading-relaxed resize-none focus:ring-2 focus:ring-helios-teal focus:border-transparent placeholder:text-stone-400 placeholder:font-sans placeholder:text-base"
          disabled={isProcessing}
        />
        
        {/* Character Count */}
        <div className={`absolute bottom-3 right-3 text-sm ${
          !isValidLength && value.length > 0 ? 'text-red-500' : 'text-stone-400'
        }`}>
          {charCount}/760 (min 25)
        </div>
      </div>

      {/* Helper Text */}
      <div className="mt-3 text-sm text-stone-500">
        <span className="font-medium">Notation:</span>{' '}
        <code className="bg-stone-100 px-1.5 py-0.5 rounded text-stone-700">?</code> one missing character,{' '}
        <code className="bg-stone-100 px-1.5 py-0.5 rounded text-stone-700">?????</code> exactly five,{' '}
        <code className="bg-stone-100 px-1.5 py-0.5 rounded text-stone-700">#</code> a gap of unknown length
      </div>

      {/* Length Warning */}
      {value.length > 0 && !isValidLength && (
        <div className="mt-2 text-sm text-red-600">
          {charCount < 25
            ? `Text too short — the model needs at least 25 characters, currently ${charCount}`
            : `Text too long (maximum 760 characters, currently ${charCount})`
          }
        </div>
      )}

      {/* Temperature Slider */}
      <div className="mt-6 flex items-center gap-4">
        <label className="text-sm font-medium text-stone-700 whitespace-nowrap">
          Restoration Sampling Temperature:
        </label>
        <input
          type="range"
          min="0.1"
          max="2.0"
          step="0.1"
          value={temperature}
          onChange={(e) => onTemperatureChange(parseFloat(e.target.value))}
          className="flex-1 h-2 bg-stone-200 rounded-lg appearance-none cursor-pointer accent-helios-teal"
          disabled={isProcessing}
        />
        <span className="text-sm font-mono text-stone-600 w-8">{temperature.toFixed(1)}</span>
      </div>

      {/* Max Gap Length — only relevant when the text contains a '#' */}
      {hasUnknownLengthGap && (
        <div className="mt-4">
          <div className="flex items-center gap-4">
            <label className="text-sm font-medium text-stone-700 whitespace-nowrap">
              Longest <code className="bg-stone-100 px-1 rounded">#</code> gap:
            </label>
            <input
              type="range"
              min="1"
              max="20"
              step="1"
              value={maxRestorationLen}
              onChange={(e) => onMaxRestorationLenChange(parseInt(e.target.value, 10))}
              className="flex-1 h-2 bg-stone-200 rounded-lg appearance-none cursor-pointer accent-helios-teal"
              disabled={isProcessing}
            />
            <span className="text-sm font-mono text-stone-600 w-16">
              {maxRestorationLen} char{maxRestorationLen === 1 ? '' : 's'}
            </span>
          </div>
          <p className="mt-1.5 text-xs text-stone-500">
            The most characters a <code className="bg-stone-100 px-1 rounded">#</code> may
            expand to. Set it a little above your estimate of the lacuna: headroom well
            past the true gap is still searched and costs time (15 took ~2× as long as 8
            for the same answer), while a value below it forces a shorter, worse
            restoration. Gaps longer than this cannot be found.
          </p>
        </div>
      )}

      {/* Action Buttons */}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <button
          onClick={onContextualize}
          disabled={isProcessing || !isValidLength}
          className="px-5 py-2.5 bg-helios-teal text-white font-medium rounded-full hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
        >
          {isProcessing ? (
            <>
              <svg className="w-4 h-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Processing...
            </>
          ) : (
            'Contextualise'
          )}
        </button>

        <button
          onClick={onAttribute}
          disabled={isProcessing || !isValidLength}
          className="px-5 py-2.5 bg-teal-600 text-white font-medium rounded-full hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          Attribute
        </button>

        <button
          onClick={onRestore}
          disabled={isProcessing || !isValidLength || !hasGaps}
          className="px-5 py-2.5 bg-teal-700 text-white font-medium rounded-full hover:bg-teal-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          title={!hasGaps ? 'Add ? or # to mark missing characters' : ''}
        >
          Restore
        </button>

        {value && (
          <button
            onClick={onClear}
            disabled={isProcessing}
            className="px-4 py-2.5 text-stone-600 hover:text-stone-800 font-medium transition-colors"
          >
            Clear
          </button>
        )}

        {/* Example Dropdown */}
        <div className="relative ml-auto">
          <button
            onClick={() => setShowExamples(!showExamples)}
            className="px-4 py-2.5 bg-stone-100 text-stone-700 font-medium rounded-full hover:bg-stone-200 transition-colors flex items-center gap-2"
          >
            Show me an example ({language === 'greek' ? 'Greek' : 'Latin'})
            <svg className={`w-4 h-4 transition-transform ${showExamples ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {showExamples && (
            <div className="absolute right-0 mt-2 w-80 bg-white rounded-lg shadow-lg border border-stone-200 py-2 z-10">
              {examples.map((example, idx) => (
                <button
                  key={idx}
                  onClick={() => handleExampleSelect(example.text)}
                  className="w-full text-left px-4 py-3 hover:bg-stone-50 transition-colors"
                >
                  <div className="font-medium text-stone-800 text-sm">{example.name}</div>
                  <div className="text-xs text-stone-500 mt-1 truncate font-serif">
                    {example.text.slice(0, 60)}...
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Model Unavailable Notice */}
      {!modelAvailable && (
        <div className="mt-4 text-sm text-stone-500 italic">
          The {language === 'greek' ? 'Greek (Ithaca)' : 'Latin (Aeneas)'} model is not currently loaded. 
          Analysis will not be available until the model is initialized.
        </div>
      )}
    </div>
  );
}
