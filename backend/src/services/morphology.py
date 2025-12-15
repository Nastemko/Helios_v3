"""Morphological analysis service for Greek and Latin words using CLTK"""

import logging
from typing import Dict, List, Optional
from cltk import NLP

logger = logging.getLogger(__name__)


class MorphologyService:
    """Service for analyzing Greek and Latin morphology using CLTK"""

    def __init__(self):
        """Initialize morphology service with CLTK"""
        self.initialized = False
        self.greek_nlp = None
        self.latin_nlp = None

        try:
            logger.info("Initializing CLTK for Ancient Greek...")
            # This will download models (~500MB-1GB) on first run
            self.greek_nlp = NLP(language_code="grc")
            logger.info("Greek NLP initialized successfully")

            logger.info("Initializing CLTK for Latin...")
            self.latin_nlp = NLP(language_code="lat")
            logger.info("Latin NLP initialized successfully")

            self.initialized = True
            logger.info("CLTK morphology service fully initialized")
        except Exception as e:
            logger.error(f"Error initializing CLTK: {e}", exc_info=True)
            logger.warning("Morphology service will run in fallback mode")

    async def analyze_word(
        self, word: str, language: str, context: Optional[str] = None
    ) -> Dict:
        """
        Analyze a Greek or Latin word

        Args:
            word: The word to analyze
            language: Language code ('grc' for Greek, 'lat' for Latin)
            context: Optional context text for disambiguation

        Returns:
            Dictionary with morphological analysis
        """
        # Clean the word (remove punctuation)
        word_clean = word.strip(".,;:!?·")

        if not self.initialized:
            return self._fallback_response(word_clean, language)

        if language == "grc":
            return await self._analyze_greek_word(word_clean, context)
        elif language == "lat":
            return await self._analyze_latin_word(word_clean, context)
        else:
            return self._fallback_response(word_clean, language)

    async def _analyze_greek_word(self, word: str, context: Optional[str]) -> Dict:
        """Analyze a Greek word using CLTK"""
        if not self.greek_nlp:
            return self._fallback_response(word, "grc")

        try:
            # Analyze the word (or context if provided)
            text_to_analyze = context if context else word
            doc = self.greek_nlp.analyze(text=text_to_analyze)

            # Find the target word in the analysis
            # If we analyzed just the word, use the first result
            # If we analyzed context, find the matching word
            word_obj = None
            if context:
                for w in doc.words:
                    if w.string.lower() == word.lower():
                        word_obj = w
                        break
            if word_obj is None and doc.words:
                word_obj = doc.words[0]

            if not word_obj:
                return self._fallback_response(word, "grc")

            # Extract morphological features (safely handle lists and missing attributes)
            morphology = {}

            def safe_get_feature(obj, attr_name):
                """Safely get a morphological feature, handling CLTK types"""
                try:
                    if hasattr(obj, attr_name):
                        value = getattr(obj, attr_name, None)
                        if value is None:
                            return None
                        # Handle CLTK MorphosyntacticFeature and similar objects
                        if hasattr(value, 'name'):
                            return str(value.name)
                        if hasattr(value, 'tag'):
                            return str(value.tag)
                        # If it's a list, extract names/tags
                        if isinstance(value, list):
                            parts = []
                            for v in value:
                                if hasattr(v, 'name'):
                                    parts.append(str(v.name))
                                elif hasattr(v, 'tag'):
                                    parts.append(str(v.tag))
                                else:
                                    parts.append(str(v))
                            return ", ".join(parts) if parts else None
                        return str(value)
                except Exception:
                    pass
                return None

            # Extract morphological features from CLTK's UDFeatureTagSet
            # CLTK stores features in word.features.features as a list of UDFeatureTag objects
            if hasattr(word_obj, 'features') and word_obj.features:
                feature_set = word_obj.features
                # Access the list of feature tags
                if hasattr(feature_set, 'features'):
                    feature_list = feature_set.features
                    for f in feature_list:
                        # Each UDFeatureTag has key (e.g., "Case") and value_label (e.g., "Genitive")
                        if hasattr(f, 'key') and hasattr(f, 'value_label'):
                            key = str(f.key).lower()
                            value = str(f.value_label)
                            if value and value.lower() not in ['none', 'unknown', '_']:
                                morphology[key] = value

            # Get lemma and POS (CLTK uses 'upos' for Universal POS)
            lemma = safe_get_feature(word_obj, "lemma") or word
            pos = safe_get_feature(word_obj, "upos") or safe_get_feature(word_obj, "pos") or "unknown"

            # Format POS for readability
            pos_display = self._format_pos(pos)

            # Build definitions based on morphology
            definitions = self._build_definitions(lemma, pos_display, morphology, "grc")

            return {
                "word": word,
                "language": "grc",
                "lemma": lemma,
                "pos": pos_display,
                "morphology": morphology,
                "definitions": definitions,
                "lexicon_url": "",  # Removed external links per user request
                "perseus_url": "",  # Removed external links per user request
            }

        except Exception as e:
            logger.error(f"Error analyzing Greek word '{word}': {e}")
            return self._fallback_response(word, "grc")

    async def _analyze_latin_word(self, word: str, context: Optional[str]) -> Dict:
        """Analyze a Latin word using CLTK"""
        if not self.latin_nlp:
            return self._fallback_response(word, "lat")

        try:
            text_to_analyze = context if context else word
            doc = self.latin_nlp.analyze(text=text_to_analyze)

            word_obj = None
            if context:
                for w in doc.words:
                    if w.string.lower() == word.lower():
                        word_obj = w
                        break
            if word_obj is None and doc.words:
                word_obj = doc.words[0]

            if not word_obj:
                return self._fallback_response(word, "lat")

            # Extract morphological features (safely handle lists and missing attributes)
            morphology = {}

            def safe_get_feature(obj, attr_name):
                """Safely get a morphological feature, handling CLTK types"""
                try:
                    if hasattr(obj, attr_name):
                        value = getattr(obj, attr_name, None)
                        if value is None:
                            return None
                        if hasattr(value, 'name'):
                            return str(value.name)
                        if hasattr(value, 'tag'):
                            return str(value.tag)
                        if isinstance(value, list):
                            parts = []
                            for v in value:
                                if hasattr(v, 'name'):
                                    parts.append(str(v.name))
                                elif hasattr(v, 'tag'):
                                    parts.append(str(v.tag))
                                else:
                                    parts.append(str(v))
                            return ", ".join(parts) if parts else None
                        return str(value)
                except Exception:
                    pass
                return None

            # Extract morphological features from CLTK's UDFeatureTagSet
            if hasattr(word_obj, 'features') and word_obj.features:
                feature_set = word_obj.features
                if hasattr(feature_set, 'features'):
                    feature_list = feature_set.features
                    for f in feature_list:
                        if hasattr(f, 'key') and hasattr(f, 'value_label'):
                            key = str(f.key).lower()
                            value = str(f.value_label)
                            if value and value.lower() not in ['none', 'unknown', '_']:
                                morphology[key] = value

            lemma = safe_get_feature(word_obj, "lemma") or word
            pos = safe_get_feature(word_obj, "upos") or safe_get_feature(word_obj, "pos") or "unknown"
            pos_display = self._format_pos(pos)

            definitions = self._build_definitions(lemma, pos_display, morphology, "lat")

            return {
                "word": word,
                "language": "lat",
                "lemma": lemma,
                "pos": pos_display,
                "morphology": morphology,
                "definitions": definitions,
                "lexicon_url": "",  # Removed external links per user request
                "perseus_url": "",  # Removed external links per user request
            }

        except Exception as e:
            logger.error(f"Error analyzing Latin word '{word}': {e}")
            return self._fallback_response(word, "lat")

    def _format_pos(self, pos: str) -> str:
        """Format part of speech for display"""
        pos_map = {
            "NOUN": "Noun",
            "VERB": "Verb",
            "ADJ": "Adjective",
            "ADV": "Adverb",
            "PRON": "Pronoun",
            "PREP": "Preposition",
            "CONJ": "Conjunction",
            "INTJ": "Interjection",
            "ART": "Article",
            "PART": "Particle",
            "DET": "Determiner",
            "NUM": "Numeral",
            "AUX": "Auxiliary",
            "SCONJ": "Subordinating Conjunction",
            "CCONJ": "Coordinating Conjunction",
            "PROPN": "Proper Noun",
        }
        return pos_map.get(pos.upper(), pos.capitalize() if pos else "Unknown")

    def _build_definitions(self, lemma: str, pos: str, morphology: dict, language: str) -> List[str]:
        """Build descriptive definitions based on morphological analysis"""
        definitions = []
        lang_name = "Greek" if language == "grc" else "Latin"
        
        # Build a grammatical form string like Perseus: "noun sg masc gen"
        form_parts = []
        
        # Start with POS
        if pos and pos.lower() != "unknown":
            form_parts.append(pos.lower())
        
        # Add morphological details in a standard order
        if morphology:
            # Number (singular, plural, dual)
            number = morphology.get("number", "")
            if number:
                # Abbreviate for cleaner display
                num_abbrev = {"singular": "sg", "plural": "pl", "dual": "dual"}
                form_parts.append(num_abbrev.get(number.lower(), number.lower()))
            
            # Gender (masculine, feminine, neuter)
            gender = morphology.get("gender", "")
            if gender:
                gen_abbrev = {"masculine": "masc", "feminine": "fem", "neuter": "neut"}
                form_parts.append(gen_abbrev.get(gender.lower(), gender.lower()))
            
            # Case (nominative, genitive, dative, accusative, vocative)
            case = morphology.get("case", "")
            if case:
                case_abbrev = {
                    "nominative": "nom", "genitive": "gen", "dative": "dat",
                    "accusative": "acc", "vocative": "voc", "ablative": "abl"
                }
                form_parts.append(case_abbrev.get(case.lower(), case.lower()))
            
            # Verb forms
            tense = morphology.get("tense", "")
            if tense:
                form_parts.append(tense.lower())
            
            mood = morphology.get("mood", "")
            if mood:
                form_parts.append(mood.lower())
            
            voice = morphology.get("voice", "")
            if voice:
                form_parts.append(voice.lower())
            
            person = morphology.get("person", "")
            if person:
                form_parts.append(f"{person}p")
        
        if form_parts:
            definitions.append(" ".join(form_parts))
        
        return definitions if definitions else [f"{lang_name} word"]

    def _fallback_response(self, word: str, language: str) -> Dict:
        """Return fallback response when CLTK is unavailable"""
        lang_name = (
            "Greek" if language == "grc" else "Latin" if language == "lat" else language
        )
        return {
            "word": word,
            "language": language,
            "lemma": word,
            "pos": "Unknown",
            "morphology": {},
            "definitions": [
                f"{lang_name} word - detailed morphological analysis is loading or unavailable"
            ],
            "lexicon_url": "",  # Removed external links per user request
            "perseus_url": "",  # Removed external links per user request
        }

    def get_lexicon_url(self, lemma: str, language: str) -> str:
        """Generate lexicon URL for a lemma"""
        return f"https://logeion.uchicago.edu/{lemma}"


# Global service instance
_morphology_service: Optional[MorphologyService] = None


def get_morphology_service() -> MorphologyService:
    """Get or create morphology service instance"""
    global _morphology_service
    if _morphology_service is None:
        _morphology_service = MorphologyService()
    return _morphology_service
