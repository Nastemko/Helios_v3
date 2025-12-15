"""Script to populate the database with Greek texts on application startup.

This script is designed to be called from main.py during FastAPI startup.
It checks if texts are already loaded and only populates if the database is empty.
"""
import logging
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from database import SessionLocal, engine, Base
from models.text import Text, TextSegment
from parsers.perseus_xml_parser import PerseusXMLParser

logger = logging.getLogger(__name__)


def is_database_populated(db: Session) -> bool:
    """Check if the database already has texts loaded."""
    count = db.query(Text).count()
    return count > 0


def populate_greek_texts(
    data_dir: Path,
    db: Session,
    limit: Optional[int] = None,
    force: bool = False
) -> dict:
    """
    Populate database with Greek texts from Perseus XML files.
    
    Args:
        data_dir: Path to the canonical-greekLit/data directory
        db: Database session
        limit: Optional limit on number of texts to process
        force: If True, clear existing texts and repopulate
        
    Returns:
        Dictionary with statistics about the operation
    """
    stats = {
        "inserted": 0,
        "skipped": 0,
        "errors": 0,
        "total_segments": 0
    }
    
    # Check if already populated
    if not force and is_database_populated(db):
        existing_count = db.query(Text).count()
        logger.info(f"Database already contains {existing_count} texts. Skipping population.")
        stats["skipped"] = existing_count
        return stats
    
    if force:
        logger.warning("Force flag set. Clearing existing texts...")
        db.query(TextSegment).delete()
        db.query(Text).delete()
        db.commit()
    
    # Verify data directory exists
    if not data_dir.exists():
        logger.error(f"Data directory not found: {data_dir}")
        return stats
    
    logger.info(f"Starting database population from {data_dir}")
    
    # Initialize parser
    parser = PerseusXMLParser(data_dir)
    
    # Get all XML files
    xml_files = parser.find_all_text_files()
    logger.info(f"Found {len(xml_files)} XML files to process")
    
    if limit:
        xml_files = xml_files[:limit]
        logger.info(f"Limited to first {limit} files")
    
    # Process each file
    for idx, xml_file in enumerate(xml_files):
        try:
            # Log progress every 100 files
            if (idx + 1) % 100 == 0:
                logger.info(f"Processing file {idx + 1}/{len(xml_files)}...")
            
            # Parse the XML file
            text_data = parser.parse_file(xml_file)
            
            if not text_data:
                logger.debug(f"Could not parse {xml_file}")
                stats["errors"] += 1
                continue
            
            # Check if text already exists (by URN)
            existing = db.query(Text).filter(Text.urn == text_data['urn']).first()
            if existing:
                logger.debug(f"Text already exists: {text_data['urn']}")
                stats["skipped"] += 1
                continue
            
            # Filter for Greek texts only (optional - can be removed if you want all languages)
            if text_data['language'] != 'grc':
                logger.debug(f"Skipping non-Greek text: {text_data['urn']}")
                continue
            
            # Create Text record
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
            
            # Create TextSegment records
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
                stats["total_segments"] += 1
            
            stats["inserted"] += 1
            
            # Commit every 50 texts to avoid memory issues
            if stats["inserted"] % 50 == 0:
                db.commit()
                logger.info(f"Committed {stats['inserted']} texts so far...")
                
        except Exception as e:
            logger.error(f"Error processing {xml_file}: {e}")
            stats["errors"] += 1
            db.rollback()
            continue
    
    # Final commit
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Error during final commit: {e}")
        db.rollback()
        raise
    
    return stats


def run_population(
    data_dir: Optional[str] = None,
    limit: Optional[int] = None,
    force: bool = False
) -> dict:
    """
    Run the database population process.
    
    This is the main entry point for populating the database.
    
    Args:
        data_dir: Optional path to data directory (uses config if not provided)
        limit: Optional limit on number of texts
        force: If True, repopulate even if database has texts
        
    Returns:
        Dictionary with statistics
    """
    from config import settings
    
    # Determine data directory
    if data_dir:
        data_path = Path(data_dir)
    else:
        data_path = Path(settings.PERSEUS_DATA_DIR)
    
    logger.info(f"Using data directory: {data_path}")
    
    # Create database session
    db = SessionLocal()
    
    try:
        stats = populate_greek_texts(
            data_dir=data_path,
            db=db,
            limit=limit,
            force=force
        )
        
        logger.info("Population complete!")
        logger.info(f"  Inserted: {stats['inserted']} texts")
        logger.info(f"  Skipped: {stats['skipped']} texts")
        logger.info(f"  Errors: {stats['errors']}")
        logger.info(f"  Total segments: {stats['total_segments']}")
        
        return stats
        
    finally:
        db.close()


async def populate_on_startup():
    """
    Async wrapper for running population on FastAPI startup.
    
    This function is designed to be called from the FastAPI startup event.
    It runs the population in a way that doesn't block the event loop.
    """
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    
    logger.info("Checking if database needs population...")
    
    # Run the synchronous population in a thread pool
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        stats = await loop.run_in_executor(executor, run_population)
    
    return stats


if __name__ == "__main__":
    """Allow running as a standalone script for testing."""
    import argparse
    import sys
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    parser = argparse.ArgumentParser(
        description="Populate database with Greek texts from Perseus XML"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        help="Path to data directory (uses config default if not provided)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of texts to process (for testing)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force repopulation even if database has texts"
    )
    
    args = parser.parse_args()
    
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)
    
    stats = run_population(
        data_dir=args.data_dir,
        limit=args.limit,
        force=args.force
    )
    
    sys.exit(0 if stats["errors"] == 0 else 1)
