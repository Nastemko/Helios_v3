"""Script to populate the database with Perseus texts"""
import sys
import logging
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models.text import Text, TextSegment
from parsers.perseus_xml_parser import PerseusXMLParser
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def populate_database(limit: int = None, dry_run: bool = False):
    """
    Populate database with Perseus texts
    
    Args:
        limit: Optional limit on number of texts to process (for testing)
        dry_run: If True, parse but don't insert into database
    """
    logger.info("Starting database population")
    
    # Create tables if they don't exist
    if not dry_run:
        logger.info("Creating database tables...")
        Base.metadata.create_all(bind=engine)
    
    # Initialize parser
    data_dir = Path(settings.PERSEUS_DATA_DIR)
    if not data_dir.exists():
        logger.error(f"Perseus data directory not found: {data_dir}")
        return
    
    parser = PerseusXMLParser(data_dir)
    
    # Parse all texts
    logger.info(f"Parsing texts from {data_dir}")
    texts_data = parser.parse_all(limit=limit)
    
    if dry_run:
        logger.info(f"DRY RUN: Would insert {len(texts_data)} texts")
        for text_data in texts_data[:5]:  # Show first 5
            logger.info(f"  - {text_data['author']}: {text_data['title']} ({len(text_data['segments'])} segments)")
        return
    
    # Insert into database
    db = SessionLocal()
    try:
        inserted_count = 0
        skipped_count = 0
        
        for text_data in texts_data:
            # Check if text already exists
            existing = db.query(Text).filter(Text.urn == text_data['urn']).first()
            if existing:
                logger.debug(f"Text already exists: {text_data['urn']}")
                skipped_count += 1
                continue
            
            # Create Text object
            text = Text(
                urn=text_data['urn'],
                author=text_data['author'],
                title=text_data['title'],
                language=text_data['language'],
                is_fragment=text_data['is_fragment'],
                text_metadata=text_data['text_metadata']
            )
            
            db.add(text)
            db.flush()  # Get the text.id
            
            # Create TextSegment objects
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
            
            inserted_count += 1
            
            if inserted_count % 50 == 0:
                logger.info(f"Inserted {inserted_count} texts...")
                db.commit()
        
        # Final commit
        db.commit()
        
        logger.info(f"Database population complete!")
        logger.info(f"  Inserted: {inserted_count} texts")
        logger.info(f"  Skipped (already exist): {skipped_count} texts")
        
        # Show statistics
        total_texts = db.query(Text).count()
        total_segments = db.query(TextSegment).count()
        logger.info(f"Database now contains:")
        logger.info(f"  {total_texts} texts")
        logger.info(f"  {total_segments} text segments")
        
    except Exception as e:
        logger.error(f"Error during database population: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def clear_database():
    """Clear all data from the database (use with caution!)"""
    logger.warning("Clearing database...")
    db = SessionLocal()
    try:
        # Delete in correct order due to foreign keys
        db.query(TextSegment).delete()
        db.query(Text).delete()
        db.commit()
        logger.info("Database cleared")
    except Exception as e:
        logger.error(f"Error clearing database: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Populate database with Perseus texts")
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of texts to process (for testing)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse files but don't insert into database"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear database before populating (use with caution!)"
    )
    
    args = parser.parse_args()
    
    if args.clear:
        response = input("Are you sure you want to clear the database? (yes/no): ")
        if response.lower() == "yes":
            clear_database()
        else:
            logger.info("Database clear cancelled")
            sys.exit(0)
    
    populate_database(limit=args.limit, dry_run=args.dry_run)

