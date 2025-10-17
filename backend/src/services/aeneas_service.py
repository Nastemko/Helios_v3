"""Aeneas AI model service for text restoration and attribution

Wraps the predictingthepast library (from predictingthepast_exp directory)
to provide text restoration, geographical attribution, and contextualization.
"""
import sys
import pickle
import logging
from pathlib import Path
from typing import Dict, Optional

import jax

# Add predictingthepast_exp to path
PRED_PATH = Path(__file__).parent.parent.parent / "predictingthepast_exp"
if PRED_PATH.exists():
    sys.path.insert(0, str(PRED_PATH))

try:
    from predictingthepast.eval import inference
    from predictingthepast.models.model import Model
    from predictingthepast.util import alphabet as util_alphabet
    AENEAS_AVAILABLE = True
except ImportError as e:
    AENEAS_AVAILABLE = False
    logging.warning(f"Aeneas dependencies not available: {e}")

from config import settings

logger = logging.getLogger(__name__)


class AeneasService:
    """Service for Aeneas AI model inference"""
    
    def __init__(self, models_dir: Path):
        """
        Initialize Aeneas service
        
        Args:
            models_dir: Directory containing model files
        """
        if not AENEAS_AVAILABLE:
            logger.error("Aeneas library not available")
            self.models = {}
            return
        
        self.models_dir = Path(models_dir)
        self.models = {}
        
        if not self.models_dir.exists():
            logger.warning(f"Models directory not found: {self.models_dir}")
            logger.warning("Aeneas features will not be available")
            return
        
        # Load models
        self._load_models()
    
    def _load_models(self):
        """Load Greek and Latin models into memory"""
        # Load Greek model
        greek_checkpoint = self.models_dir / "ithaca_153143996_2.pkl"
        greek_dataset = self.models_dir / "iphi.json"
        greek_retrieval = self.models_dir / "iphi_emb_xid153143996.pkl"
        
        if all(p.exists() for p in [greek_checkpoint, greek_dataset, greek_retrieval]):
            try:
                logger.info("Loading Greek (Aeneas/Ithaca) model...")
                self.models['greek'] = self._load_checkpoint(
                    greek_checkpoint,
                    greek_dataset,
                    greek_retrieval,
                    'greek'
                )
                logger.info("Greek model loaded successfully")
            except Exception as e:
                logger.error(f"Error loading Greek model: {e}")
        
        # Load Latin model
        latin_checkpoint = self.models_dir / "aeneas_117149994_2.pkl"
        latin_dataset = self.models_dir / "led.json"
        latin_retrieval = self.models_dir / "led_emb_xid117149994.pkl"
        
        if all(p.exists() for p in [latin_checkpoint, latin_dataset, latin_retrieval]):
            try:
                logger.info("Loading Latin (Aeneas) model...")
                self.models['latin'] = self._load_checkpoint(
                    latin_checkpoint,
                    latin_dataset,
                    latin_retrieval,
                    'latin'
                )
                logger.info("Latin model loaded successfully")
            except Exception as e:
                logger.error(f"Error loading Latin model: {e}")
        
        if not self.models:
            logger.warning("No Aeneas models loaded. Download model files to enable AI features.")
    
    def _load_checkpoint(
        self,
        checkpoint_path: Path,
        dataset_path: Path,
        retrieval_path: Path,
        language: str
    ) -> Dict:
        """
        Load a model checkpoint
        
        Args:
            checkpoint_path: Path to checkpoint pickle
            dataset_path: Path to dataset JSON
            retrieval_path: Path to retrieval embeddings pickle
            language: 'greek' or 'latin'
        
        Returns:
            Dictionary with model components
        """
        # Load checkpoint
        with open(checkpoint_path, 'rb') as f:
            checkpoint = pickle.load(f)
        
        # Load model parameters
        params = jax.device_put(checkpoint['params'])
        model = Model(**checkpoint['model_config'])
        
        # Load alphabet
        if language == 'latin':
            alphabet = util_alphabet.LatinAlphabet()
        elif language == 'greek':
            alphabet = util_alphabet.GreekAlphabet()
        else:
            raise ValueError(f"Unknown language: {language}")
        
        # Load dataset and retrieval embeddings
        dataset = inference.load_dataset(str(dataset_path))
        retrieval = inference.load_retrieval(str(retrieval_path))
        
        return {
            'model': model,
            'params': params,
            'alphabet': alphabet,
            'region_map': checkpoint['region_map'],
            'vocab_char_size': checkpoint['model_config']['vocab_char_size'],
            'dataset': dataset,
            'retrieval': retrieval
        }
    
    async def restore_text(
        self,
        text: str,
        language: str,
        beam_width: int = 100,
        temperature: float = 1.0,
        max_len: int = 15
    ) -> Dict:
        """
        Restore damaged text (marked with # for missing characters)
        
        Args:
            text: Input text with # marking missing characters
            language: 'greek' or 'latin'
            beam_width: Beam width for beam search
            temperature: Sampling temperature
            max_len: Maximum length of unknown restoration
        
        Returns:
            Dictionary with restoration results
        
        Example:
            Input: "μῆνιν ἄ#ιδε θεὰ"
            Output: Multiple restoration options with probabilities
        """
        if language not in self.models:
            return {
                "error": f"Model not loaded for language: {language}",
                "available_languages": list(self.models.keys())
            }
        
        model_data = self.models[language]
        
        try:
            restoration = inference.restore(
                text,
                forward=model_data['model'].apply,
                params=model_data['params'],
                alphabet=model_data['alphabet'],
                vocab_char_size=model_data['vocab_char_size'],
                beam_width=beam_width,
                temperature=temperature,
                unk_restoration_max_len=max_len
            )
            
            return restoration.build_json()
        except Exception as e:
            logger.error(f"Error during restoration: {e}")
            return {"error": str(e)}
    
    async def attribute_text(self, text: str, language: str) -> Dict:
        """
        Predict geographical origin and date of text
        
        Args:
            text: Input text
            language: 'greek' or 'latin'
        
        Returns:
            Dictionary with attribution results
        """
        if language not in self.models:
            return {
                "error": f"Model not loaded for language: {language}",
                "available_languages": list(self.models.keys())
            }
        
        model_data = self.models[language]
        
        try:
            attribution = inference.attribute(
                text,
                forward=model_data['model'].apply,
                params=model_data['params'],
                alphabet=model_data['alphabet'],
                vocab_char_size=model_data['vocab_char_size']
            )
            
            return attribution.build_json()
        except Exception as e:
            logger.error(f"Error during attribution: {e}")
            return {"error": str(e)}
    
    async def contextualize_text(self, text: str, language: str) -> Dict:
        """
        Find similar inscriptions and contextual parallels
        
        Args:
            text: Input text
            language: 'greek' or 'latin'
        
        Returns:
            Dictionary with similar inscriptions
        """
        if language not in self.models:
            return {
                "error": f"Model not loaded for language: {language}",
                "available_languages": list(self.models.keys())
            }
        
        model_data = self.models[language]
        
        try:
            contextualization = inference.contextualize(
                text,
                model_data['dataset'],
                model_data['retrieval'],
                model_data['model'].apply,
                model_data['params'],
                model_data['alphabet'],
                model_data['region_map']
            )
            
            return contextualization.build_json()
        except Exception as e:
            logger.error(f"Error during contextualization: {e}")
            return {"error": str(e)}
    
    def is_available(self, language: Optional[str] = None) -> bool:
        """
        Check if Aeneas is available
        
        Args:
            language: Optional language to check. If None, checks if any model is loaded.
        
        Returns:
            True if available, False otherwise
        """
        if not AENEAS_AVAILABLE:
            return False
        
        if language:
            return language in self.models
        
        return len(self.models) > 0


# Global service instance
_aeneas_service: Optional[AeneasService] = None


def initialize_aeneas_service(models_dir: Path):
    """Initialize the global Aeneas service"""
    global _aeneas_service
    _aeneas_service = AeneasService(models_dir)


def get_aeneas_service() -> Optional[AeneasService]:
    """Get the Aeneas service instance"""
    return _aeneas_service

