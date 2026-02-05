"""Optimized script to populate database with PHI inscriptions from iphi.json.

This script applies all lessons learned from Perseus population optimization:
- SQLAlchemy 2.x compatible with modern query patterns
- PostgreSQL ON CONFLICT DO NOTHING to eliminate SELECT queries
- Prefetched URN cache for efficient duplicate detection
- Batched processing using itertools.batched
- Configurable parameters with dataclasses
- Comprehensive error handling and statistics
"""

import itertools
import json
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from config import settings
from database import Base, SessionLocal, engine
from models.text import Text, TextSegment

logger = logging.getLogger(__name__)


@dataclass
class PHIConfig:
    """Configuration for PHI inscription loading."""

    phi_json_path: Optional[str] = None
    limit: Optional[int] = None
    dry_run: bool = False
    batch_size: int = 500
    fail_fast: bool = True
    force: bool = False


@dataclass
class PHIStats:
    """Statistics for PHI inscription operation."""

    inserted: int = 0
    skipped: int = 0
    errors: int = 0
    total_segments: int = 0
    processing_time: float = 0.0
    files_processed: int = 0


class PHIInscriptionLoader:
    """Handles PHI inscription loading with batched operations and optimized queries."""

    def __init__(self, config: PHIConfig):
        self.config = config
        self.stats = PHIStats()
        self.existing_phi_local_ids = set()

    def get_json_path(self) -> Path:
        """Get the path to the PHI JSON file."""
        if self.config.phi_json_path:
            return Path(self.config.phi_json_path)

        # Use default path from settings
        phi_dir = Path("iphi")  # Fallback if settings missing
        try:
            phi_dir = Path(settings.assets.INSCRIPTIONS_DIR)
        except AttributeError:
            # Use fallback path if INSCRIPTIONS_DIR not defined
            pass

        return phi_dir / "iphi.json"

    def prefetch_existing_phi_local_ids(self, db: Session) -> None:
        """Prefetch existing PHI local_ids to avoid individual database queries."""
        logger.info("Prefetching existing PHI local_ids...")

        # Only fetch PHI texts (source = 'PHI') for efficiency
        existing_phi = db.execute(
            select(Text.local_id).filter(Text.source == "PHI")
        ).all()

        self.existing_phi_local_ids = {row.local_id for row in existing_phi}
        logger.info(
            f"Prefetched {len(self.existing_phi_local_ids)} existing PHI local_ids"
        )

    def is_database_populated_with_phi(self, db: Session) -> bool:
        """Check if database already has PHI inscriptions."""
        if self.existing_phi_local_ids:
            return len(self.existing_phi_local_ids) > 0
        result = db.scalar(
            select(func.count(Text.id)).filter(Text.source == "PHI").limit(1)
        )
        return result is not None and result > 0

    def should_process_inscription(self, inscription: Dict) -> bool:
        """Check if inscription should be processed based on existing local_id cache."""
        phi_id = inscription.get("id")
        if not phi_id:
            return False

        return str(phi_id) not in self.existing_phi_local_ids

    def prepare_batch_data(self, inscriptions: List[Dict]) -> List[Dict]:
        """Prepare batch data for database insertion."""
        batch_data = []

        for inscription in inscriptions:
            try:
                if self.should_process_inscription(inscription):
                    batch_data.append(inscription)
                    self.stats.files_processed += 1
                else:
                    self.stats.skipped += 1

            except Exception as e:
                logger.error(
                    f"Error preparing inscription {inscription.get('id', 'unknown')}: {e}"
                )
                self.stats.errors += 1
                if self.config.fail_fast:
                    raise RuntimeError(
                        f"Failed to prepare inscription. Stopping due to fail_fast=True."
                    )

        return batch_data

    def create_segments_for_text(
        self, db: Session, inscription: Dict, text_id: int
    ) -> None:
        """Create text segments for an inscription."""
        content = inscription.get("text", "").strip()

        if not content:
            return

        # Split on periods to create segments, keeping reasonable chunks
        sentences = [s.strip() for s in content.split(".") if s.strip()]

        if sentences:
            for seq, sentence in enumerate(sentences, 1):
                segment = TextSegment(
                    text_id=text_id,
                    book="1",
                    line=str(seq),
                    reference=f"1.{seq}",
                    content=sentence,
                    sequence=seq,
                )
                db.add(segment)
                self.stats.total_segments += 1
        else:
            # Single segment for whole inscription if no periods
            segment = TextSegment(
                text_id=text_id,
                book="1",
                line="1",
                reference="1.1",
                content=content,
                sequence=1,
            )
            db.add(segment)
            self.stats.total_segments += 1

    def insert_batch(self, db: Session, batch_data: List[Dict]) -> None:
        """Insert a batch of PHI inscriptions with ON CONFLICT optimization."""
        if not batch_data:
            return

        # Prepare values for bulk insert using SQLAlchemy models
        inscription_values = []
        for inscription in batch_data:
            phi_id = inscription.get("id")
            local_id = str(phi_id)

            # Build title
            title = f"PHI {phi_id}"
            region_sub = inscription.get("region_sub")
            region_main = inscription.get("region_main")

            if region_sub:
                title = f"{region_sub} - PHI {phi_id}"
            elif region_main:
                title = f"{region_main} - PHI {phi_id}"

            inscription_values.append(
                {
                    "local_id": local_id,
                    "source": "PHI",
                    "author": "[Inscription]",
                    "title": title,
                    "language": "grc",
                    "is_fragment": True,
                    "text_metadata": {
                        "text_type": "inscription",
                        "phi_id": phi_id,
                        "source": "Packard Humanities Institute",
                        "region_main": region_main,
                        "region_main_id": inscription.get("region_main_id"),
                        "region_sub": region_sub,
                        "region_sub_id": inscription.get("region_sub_id"),
                        "date_str": inscription.get("date_str"),
                        "date_min": inscription.get("date_min"),
                        "date_max": inscription.get("date_max"),
                        "date_circa": inscription.get("date_circa"),
                        "metadata_raw": inscription.get("metadata"),
                    },
                }
            )

        # Use SQLAlchemy's PostgreSQL insert() dialect
        stmt = (
            insert(Text)
            .values(inscription_values)
            .on_conflict_do_nothing(index_elements=["local_id"])
            .returning(Text.id, Text.local_id)
        )

        try:
            result = db.execute(stmt)
            inserted_texts = result.fetchall()  # This will be [] if all conflicted

            # Handle empty results gracefully - this is the key fix
            if not inserted_texts:
                logger.debug(
                    "All PHI inscriptions in batch already exist (no new rows inserted)"
                )
                # Mark all as skipped
                self.stats.skipped += len(batch_data)
                return

            # Get mapping of local_id to ID for inserted texts
            local_id_to_id = {row.local_id: row.id for row in inserted_texts}

            # Create segments for successfully inserted texts
            for inscription in batch_data:
                phi_id = inscription.get("id")
                local_id = str(phi_id)

                if local_id in local_id_to_id:
                    text_id = local_id_to_id[local_id]
                    self.create_segments_for_text(db, inscription, text_id)
                    self.stats.inserted += 1
                    self.existing_phi_local_ids.add(local_id)
                else:
                    # Already existed
                    self.stats.skipped += 1

        except Exception as e:
            logger.error(f"Error during batch insert: {e}")
            raise

    def process_inscription_batch(
        self, db: Session, batch_inscriptions: List[Dict]
    ) -> None:
        """Process a batch of inscriptions in a single transaction."""
        try:
            # Prepare and insert batch data
            batch_data = self.prepare_batch_data(batch_inscriptions)

            if self.config.dry_run:
                logger.info(
                    f"DRY RUN: Would insert {len(batch_data)} inscriptions from this batch"
                )
                for inscription in batch_data[:3]:  # Show first 3
                    phi_id = inscription.get("id", "unknown")
                    region = (
                        inscription.get("region_sub")
                        or inscription.get("region_main")
                        or "Unknown"
                    )
                    date = inscription.get("date_str", "No date")
                    text_preview = (
                        inscription.get("text", "")[:50] + "..."
                        if len(inscription.get("text", "")) > 50
                        else inscription.get("text", "")
                    )
                    logger.info(f"  PHI {phi_id}: {region} - {date}")
                    logger.info(f"    Text: {text_preview}")
                return

            # Insert all data in this batch as a single transaction
            self.insert_batch(db, batch_data)

            # Commit entire batch at once
            db.commit()
            logger.info(
                f"Successfully committed batch with {len(batch_data)} inscriptions"
            )

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            db.rollback()
            self.stats.errors += len(batch_inscriptions)
            if self.config.fail_fast:
                raise RuntimeError(
                    f"Batch processing failed. Stopping due to fail_fast=True."
                )

    def run_loading(self, db: Session) -> PHIStats:
        """Main PHI loading method with batched processing."""
        start_time = time.time()

        # Get JSON file path
        json_path = self.get_json_path()
        if not json_path.exists():
            raise FileNotFoundError(f"PHI JSON file not found: {json_path}")

        # Load JSON data
        logger.info(f"Loading PHI data from {json_path}")
        with open(json_path, "r", encoding="utf-8") as f:
            inscriptions = json.load(f)

        total_count = len(inscriptions)
        logger.info(f"Found {total_count} inscriptions in JSON file")

        if self.config.limit:
            inscriptions = inscriptions[: self.config.limit]
            logger.info(f"Limiting to first {self.config.limit} inscriptions")

        # Prefetch existing local_ids
        self.prefetch_existing_phi_local_ids(db)

        # Check if already populated
        if not self.config.force and self.is_database_populated_with_phi(db):
            logger.info(
                f"Database already contains {len(self.existing_phi_local_ids)} PHI inscriptions. Skipping loading."
            )
            self.stats.skipped = len(self.existing_phi_local_ids)
            return self.stats

        # Clear existing if force mode
        if self.config.force:
            self.clear_inscriptions(db)

        # Process inscriptions in batches
        batch_size = self.config.batch_size
        total_batches = (len(inscriptions) + batch_size - 1) // batch_size

        for batch_num, batch_inscriptions in enumerate(
            itertools.batched(inscriptions, batch_size), start=1
        ):
            logger.info(
                f"Processing batch {batch_num}/{total_batches} ({len(batch_inscriptions)} inscriptions)..."
            )
            self.process_inscription_batch(db, list(batch_inscriptions))

        # Calculate processing time
        self.stats.processing_time = time.time() - start_time

        return self.stats

    def clear_inscriptions(self, db: Session) -> None:
        """Remove all PHI inscriptions from database."""
        logger.warning("Clearing all PHI inscriptions from database...")

        # Find all inscription texts by source
        inscription_texts = db.execute(select(Text).filter(Text.source == "PHI")).all()

        count = len(inscription_texts)

        for text in inscription_texts:
            db.delete(text)  # Segments cascade deleted

        db.commit()
        logger.info(f"Deleted {count} PHI inscriptions")


def load_phi_inscriptions(
    phi_json_path: Optional[str] = None,
    limit: Optional[int] = None,
    dry_run: bool = False,
    batch_size: int = 500,
    fail_fast: bool = True,
) -> PHIStats:
    """
    Load PHI inscriptions into Helios database with optimizations.

    Args:
        phi_json_path: Path to iphi.json file
        limit: Optional limit on number of inscriptions to load
        dry_run: If True, don't actually insert into database
        batch_size: Number of records to commit at once
        fail_fast: Whether to stop on first error

    Returns:
        PHIStats with operation results
    """
    config = PHIConfig(
        phi_json_path=phi_json_path,
        limit=limit,
        dry_run=dry_run,
        batch_size=batch_size,
        fail_fast=fail_fast,
    )

    # Ensure tables exist
    logger.info("Creating database tables if needed...")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        loader = PHIInscriptionLoader(config)
        stats = loader.run_loading(db)

        logger.info("=" * 50)
        logger.info("PHI inscription import complete!")
        logger.info(f"  Inserted: {stats.inserted}")
        logger.info(f"  Skipped (already exist): {stats.skipped}")
        logger.info(f"  Errors: {stats.errors}")
        logger.info(f"  Total segments: {stats.total_segments}")
        logger.info(f"  Processing time: {stats.processing_time:.2f} seconds")

        # Show database totals
        total_texts = db.scalar(select(func.count(Text.id)))
        total_segments = db.scalar(select(func.count(TextSegment.id)))
        inscription_count = db.scalar(
            select(func.count(Text.id)).filter(Text.source == "PHI")
        )

        logger.info("=" * 50)
        logger.info("Database totals:")
        logger.info(f"  Total texts: {total_texts}")
        logger.info(f"  Total inscriptions: {inscription_count}")
        logger.info(f"  Total segments: {total_segments}")

        return stats

    except Exception as e:
        logger.error(f"Fatal error during import: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def clear_inscriptions():
    """Remove all PHI inscriptions from database (use with caution!)."""
    logger.warning("Clearing all PHI inscriptions from database...")
    db = SessionLocal()
    try:
        # Use the optimized class-based approach
        loader = PHIInscriptionLoader(PHIConfig())
        loader.clear_inscriptions(db)
        logger.info("PHI inscriptions cleared successfully")
    except Exception as e:
        logger.error(f"Error clearing inscriptions: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def initialize_phi_inscriptions():
    """
    Load PHI inscriptions into database on FastAPI startup.

    Optimized version with SQLAlchemy 2.x compatibility and all performance improvements.
    """
    logger.info("Initializing PHI inscriptions...")

    try:
        stats = load_phi_inscriptions(
            phi_json_path=None,  # Use default path
            limit=None,  # No limits for production
            dry_run=False,
            batch_size=500,  # Default batch size
            fail_fast=False,  # Continue on errors during startup
        )
        logger.info("PHI inscriptions initialized successfully")
        return {"status": "success", "stats": stats}
    except Exception as e:
        logger.error(f"Error initializing PHI inscriptions: {e}")
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    """CLI interface for PHI inscription loading."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Load PHI inscriptions into database (optimized)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Load all inscriptions
  python load_phi_inscriptions.py

  # Dry run to see what would be processed
  python load_phi_inscriptions.py --dry-run

  # Process only first 100 inscriptions
  python load_phi_inscriptions.py --limit 100

  # Force reload (clear existing)
  python load_phi_inscriptions.py --force

  # Custom batch size
  python load_phi_inscriptions.py --batch-size 200
        """,
    )

    parser.add_argument(
        "--phi-json-path",
        type=str,
        help="Path to iphi.json file (uses default if not provided)",
    )
    parser.add_argument(
        "--limit", type=int, help="Limit number of inscriptions to load (for testing)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse files but don't insert into database",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Batch size for database transactions (default: 500)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear existing inscriptions and reload (use with caution!)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing on individual errors (default: fail-fast)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Safety check for force operation
    if args.force:
        response = input(
            "Are you sure you want to clear all existing PHI inscriptions and reload? (yes/no): "
        )
        if response.lower() != "yes":
            logger.info("Force operation cancelled")
            sys.exit(0)

    try:
        stats = load_phi_inscriptions(
            phi_json_path=args.phi_json_path,
            limit=args.limit,
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            fail_fast=not args.continue_on_error,
        )
        sys.exit(0 if stats.errors == 0 else 1)
    except KeyboardInterrupt:
        logger.info("PHI loading interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"PHI loading failed: {e}")
        sys.exit(1)
