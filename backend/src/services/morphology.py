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
        self,
        word: str,
        language: str,
        context: Optional[str] = None
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
        word_clean = word.strip('.,;:!?·')
        
        if not self.initialized:
            return self._fallback_response(word_clean, language)
        
        if language == 'grc':
            return await self._analyze_greek_word(word_clean, context)
        elif language == 'lat':
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
                """Safely get a morphological feature, handling lists and exceptions"""
                try:
                    if hasattr(obj, attr_name):
                        value = getattr(obj, attr_name, None)
                        if value:
                            # If it's a list, join the values
                            if isinstance(value, list):
                                return ', '.join(str(v) for v in value)
                            return str(value)
                except Exception:
                    pass
                return None
            
            # Extract all possible morphological features
            for feature in ['case', 'number', 'gender', 'tense', 'mood', 'voice', 'person', 'degree']:
                value = safe_get_feature(word_obj, feature)
                if value:
                    morphology[feature] = value
            
            # Get lemma and POS
            lemma = safe_get_feature(word_obj, 'lemma') or word
            pos = safe_get_feature(word_obj, 'pos') or "unknown"
            
            # Format POS for readability
            pos_display = self._format_pos(pos)
            
            return {
                "word": word,
                "language": "grc",
                "lemma": lemma,
                "pos": pos_display,
                "morphology": morphology,
                "definitions": [
                    f"See Logeion for detailed definitions of {lemma}"
                ],
                "lexicon_url": f"https://logeion.uchicago.edu/{lemma}",
                "perseus_url": f"https://www.perseus.tufts.edu/hopper/morph?l={word}&la=greek"
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
                """Safely get a morphological feature, handling lists and exceptions"""
                try:
                    if hasattr(obj, attr_name):
                        value = getattr(obj, attr_name, None)
                        if value:
                            if isinstance(value, list):
                                return ', '.join(str(v) for v in value)
                            return str(value)
                except Exception:
                    pass
                return None
            
            # Extract all possible morphological features
            for feature in ['case', 'number', 'gender', 'tense', 'mood', 'voice', 'person', 'degree']:
                value = safe_get_feature(word_obj, feature)
                if value:
                    morphology[feature] = value
            
            lemma = safe_get_feature(word_obj, 'lemma') or word
            pos = safe_get_feature(word_obj, 'pos') or "unknown"
            pos_display = self._format_pos(pos)
            
            return {
                "word": word,
                "language": "lat",
                "lemma": lemma,
                "pos": pos_display,
                "morphology": morphology,
                "definitions": [
                    f"See Logeion for detailed definitions of {lemma}"
                ],
                "lexicon_url": f"https://logeion.uchicago.edu/{lemma}",
                "perseus_url": f"https://www.perseus.tufts.edu/hopper/morph?l={word}&la=latin"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing Latin word '{word}': {e}")
            return self._fallback_response(word, "lat")
    
    def _format_pos(self, pos: str) -> str:
        """Format part of speech for display"""
        pos_map = {
            'NOUN': 'Noun',
            'VERB': 'Verb',
            'ADJ': 'Adjective',
            'ADV': 'Adverb',
            'PRON': 'Pronoun',
            'PREP': 'Preposition',
            'CONJ': 'Conjunction',
            'INTJ': 'Interjection',
            'ART': 'Article',
            'PART': 'Particle',
        }
        return pos_map.get(pos.upper(), pos.capitalize() if pos else "Unknown")
    
    def _fallback_response(self, word: str, language: str) -> Dict:
        """Return fallback response when CLTK is unavailable"""
        lang_name = "Greek" if language == "grc" else "Latin" if language == "lat" else language
        return {
            "word": word,
            "language": language,
            "lemma": word,
            "pos": "unknown",
            "morphology": {
                "note": f"CLTK morphological analysis unavailable. Using fallback mode."
            },
            "definitions": [
                f"Click the lexicon link below to see definitions for this {lang_name} word"
            ],
            "lexicon_url": f"https://logeion.uchicago.edu/{word}",
            "perseus_url": f"https://www.perseus.tufts.edu/hopper/morph?l={word}&la={'greek' if language == 'grc' else 'latin'}"
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
