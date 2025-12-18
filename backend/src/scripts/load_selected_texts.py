"""Script to load selected Greek texts into the database."""
import sys
import logging
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models.text import Text, TextSegment
from parsers.perseus_xml_parser import PerseusXMLParser

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Authors to load (TLG codes)
SELECTED_AUTHORS = {
    "tlg0012": "Homer",
    "tlg0013": "Homeric Hymns", 
    "tlg0085": "Aeschylus",
    "tlg0011": "Sophocles",
    "tlg0006": "Euripides",
    "tlg0003": "Thucydides",
    "tlg0016": "Herodotus",
}


def load_selected_texts(data_dir: Path):
    """Load texts from selected authors only."""
    
    # Create tables if needed
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    parser = PerseusXMLParser(data_dir)
    
    stats = {"inserted": 0, "skipped": 0, "errors": 0, "segments": 0}
    
    try:
        for tlg_code, author_name in SELECTED_AUTHORS.items():
            author_dir = data_dir / tlg_code
            
            if not author_dir.exists():
                logger.warning(f"Directory not found: {author_dir}")
                continue
                
            logger.info(f"Processing {author_name} ({tlg_code})...")
            
            # Find all Greek XML files for this author
            for xml_file in author_dir.rglob("*-grc*.xml"):
                try:
                    text_data = parser.parse_file(xml_file)
                    
                    if not text_data:
                        logger.debug(f"Could not parse: {xml_file.name}")
                        stats["errors"] += 1
                        continue
                    
                    # Skip if already exists
                    existing = db.query(Text).filter(Text.urn == text_data['urn']).first()
                    if existing:
                        logger.debug(f"Already exists: {text_data['title']}")
                        stats["skipped"] += 1
                        continue
                    
                    # Create text record
                    text = Text(
                        urn=text_data['urn'],
                        author=text_data['author'],
                        title=text_data['title'],
                        language=text_data['language'],
                        is_fragment=text_data['is_fragment'],
                        text_metadata=text_data['text_metadata']
                    )
                    db.add(text)
                    db.flush()
                    
                    # Create segments
                    for seg_data in text_data['segments']:
                        segment = TextSegment(
                            text_id=text.id,
                            book=seg_data['book'],
                            line=seg_data['line'],
                            reference=seg_data['reference'],
                            content=seg_data['content'],
                            sequence=seg_data['sequence']
                        )
                        db.add(segment)
                        stats["segments"] += 1
                    
                    stats["inserted"] += 1
                    logger.info(f"  Loaded: {text_data['title']} ({len(text_data['segments'])} segments)")
                    
                except Exception as e:
                    logger.error(f"Error processing {xml_file}: {e}")
                    stats["errors"] += 1
                    continue
            
            # Commit after each author
            db.commit()
        
        logger.info("=" * 50)
        logger.info(f"Loading complete!")
        logger.info(f"  Inserted: {stats['inserted']} texts")
        logger.info(f"  Skipped: {stats['skipped']} (already exist)")
        logger.info(f"  Errors: {stats['errors']}")
        logger.info(f"  Total segments: {stats['segments']}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()
    
    return stats


if __name__ == "__main__":
    # Default data directory
    data_dir = Path(__file__).parent.parent.parent.parent / "canonical-greekLit" / "data"
    
    if not data_dir.exists():
        # Try alternative path
        data_dir = Path("/Users/nastemko/Helios_v3/canonical-greekLit/data")
    
    logger.info(f"Data directory: {data_dir}")
    logger.info(f"Loading texts for: {', '.join(SELECTED_AUTHORS.values())}")
    
    load_selected_texts(data_dir)

