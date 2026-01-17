"""Script to populate the database with PHI inscriptions from iphi.json"""
import sys
import json
import logging
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from models.text import Text, TextSegment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def load_phi_inscriptions(
    phi_json_path: str = None,
    limit: int = None,
    dry_run: bool = False,
    batch_size: int = 500
):
    """
    Load PHI inscriptions into Helios database
    
    Args:
        phi_json_path: Path to iphi.json file
        limit: Optional limit on number of inscriptions to load
        dry_run: If True, don't actually insert into database
        batch_size: Number of records to commit at once
    """
    # Default path - look in the iphi directory
    if phi_json_path is None:
        phi_json_path = Path(__file__).parent.parent.parent.parent / "iphi" / "train" / "data" / "iphi.json"
    
    phi_json_path = Path(phi_json_path)
    
    if not phi_json_path.exists():
        logger.error(f"PHI JSON file not found: {phi_json_path}")
        logger.info("Make sure iphi.json is in the iphi/train/data/ directory")
        return
    
    # Load JSON
    logger.info(f"Loading PHI data from {phi_json_path}")
    with open(phi_json_path, 'r', encoding='utf-8') as f:
        inscriptions = json.load(f)
    
    total_count = len(inscriptions)
    logger.info(f"Found {total_count} inscriptions in JSON file")
    
    if limit:
        inscriptions = inscriptions[:limit]
        logger.info(f"Limiting to first {limit} inscriptions")
    
    if dry_run:
        logger.info("DRY RUN - showing first 5 inscriptions:")
        for insc in inscriptions[:5]:
            region = insc.get('region_sub') or insc.get('region_main') or 'Unknown'
            date = insc.get('date_str', 'No date')
            text_preview = insc.get('text', '')[:50] + '...' if len(insc.get('text', '')) > 50 else insc.get('text', '')
            logger.info(f"  PHI {insc['id']}: {region} - {date}")
            logger.info(f"    Text: {text_preview}")
        return
    
    # Ensure tables exist
    logger.info("Creating database tables if needed...")
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        inserted = 0
        skipped = 0
        errors = 0
        
        for idx, insc in enumerate(inscriptions):
            try:
                phi_id = insc.get('id')
                if not phi_id:
                    errors += 1
                    continue
                
                # Create URN for inscription
                urn = f"urn:phi:{phi_id}"
                
                # Check if exists
                existing = db.query(Text).filter(Text.urn == urn).first()
                if existing:
                    skipped += 1
                    continue
                
                # Build title from metadata
                title = f"PHI {phi_id}"
                if insc.get('region_sub'):
                    title = f"{insc['region_sub']} - PHI {phi_id}"
                elif insc.get('region_main'):
                    title = f"{insc['region_main']} - PHI {phi_id}"
                
                # Create Text record
                text = Text(
                    urn=urn,
                    author="[Inscription]",  # Anonymous for inscriptions
                    title=title,
                    language="grc",
                    is_fragment=True,  # Inscriptions are often fragmentary
                    text_metadata={
                        "text_type": "inscription",
                        "phi_id": phi_id,
                        "source": "Packard Humanities Institute",
                        "region_main": insc.get('region_main'),
                        "region_main_id": insc.get('region_main_id'),
                        "region_sub": insc.get('region_sub'),
                        "region_sub_id": insc.get('region_sub_id'),
                        "date_str": insc.get('date_str'),
                        "date_min": insc.get('date_min'),
                        "date_max": insc.get('date_max'),
                        "date_circa": insc.get('date_circa'),
                        "metadata_raw": insc.get('metadata'),
                    }
                )
                
                db.add(text)
                db.flush()  # Get the text.id
                
                # Create segments - split by sentences or treat as single segment
                content = insc.get('text', '').strip()
                if content:
                    # Split on periods to create segments, keeping reasonable chunks
                    sentences = [s.strip() for s in content.split('.') if s.strip()]
                    
                    if sentences:
                        for seq, sentence in enumerate(sentences, 1):
                            segment = TextSegment(
                                text_id=text.id,
                                book="1",
                                line=str(seq),
                                reference=f"1.{seq}",
                                content=sentence,
                                sequence=seq
                            )
                            db.add(segment)
                    else:
                        # Single segment for whole inscription if no periods
                        segment = TextSegment(
                            text_id=text.id,
                            book="1",
                            line="1",
                            reference="1.1",
                            content=content,
                            sequence=1
                        )
                        db.add(segment)
                
                inserted += 1
                
                # Commit in batches for performance
                if inserted % batch_size == 0:
                    db.commit()
                    logger.info(f"Progress: {inserted} inserted, {skipped} skipped, {errors} errors ({idx + 1}/{len(inscriptions)})")
                    
            except Exception as e:
                logger.warning(f"Error processing inscription {insc.get('id', 'unknown')}: {e}")
                errors += 1
                db.rollback()
                continue
        
        # Final commit
        db.commit()
        
        logger.info("=" * 50)
        logger.info("PHI inscription import complete!")
        logger.info(f"  Inserted: {inserted}")
        logger.info(f"  Skipped (already exist): {skipped}")
        logger.info(f"  Errors: {errors}")
        
        # Show database totals
        total_texts = db.query(Text).count()
        total_segments = db.query(TextSegment).count()
        # Count inscriptions by checking URN prefix (works with both SQLite and Postgres)
        inscription_count = db.query(Text).filter(
            Text.urn.like('urn:phi:%')
        ).count()
        
        logger.info("=" * 50)
        logger.info("Database totals:")
        logger.info(f"  Total texts: {total_texts}")
        logger.info(f"  Total inscriptions: {inscription_count}")
        logger.info(f"  Total segments: {total_segments}")
        
    except Exception as e:
        logger.error(f"Fatal error during import: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def clear_inscriptions():
    """Remove all inscriptions from the database (use with caution!)"""
    logger.warning("Clearing all inscriptions from database...")
    db = SessionLocal()
    try:
        # Find all inscription texts by URN prefix (works with both SQLite and Postgres)
        inscription_texts = db.query(Text).filter(
            Text.urn.like('urn:phi:%')
        ).all()
        
        count = len(inscription_texts)
        
        for text in inscription_texts:
            # Segments will be cascade deleted
            db.delete(text)
        
        db.commit()
        logger.info(f"Deleted {count} inscriptions")
    except Exception as e:
        logger.error(f"Error clearing inscriptions: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Load PHI inscriptions into Helios database")
    parser.add_argument(
        "--json-path",
        type=str,
        help="Path to iphi.json file (defaults to iphi/train/data/iphi.json)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of inscriptions to load (for testing)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't insert, just preview what would be loaded"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Number of records to commit at once (default: 500)"
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear all existing inscriptions before loading (use with caution!)"
    )
    
    args = parser.parse_args()
    
    if args.clear:
        response = input("Are you sure you want to clear all inscriptions? (yes/no): ")
        if response.lower() == "yes":
            clear_inscriptions()
        else:
            logger.info("Clear cancelled")
            sys.exit(0)
    
    load_phi_inscriptions(
        phi_json_path=args.json_path,
        limit=args.limit,
        dry_run=args.dry_run,
        batch_size=args.batch_size
    )

