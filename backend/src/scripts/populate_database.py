"""Unified script to populate database with Perseus texts.

This script replaces both populate_on_startup.py and populate_texts.py with
a superior implementation that eliminates duplicate key constraint violations
through atomic database operations.

Features:
- Prefetch existing URNs to avoid individual database queries
- Optimized batching using itertools.batched for efficient processing
- PostgreSQL ON CONFLICT DO NOTHING to eliminate SELECT queries
- SQLAlchemy 2.x compatible for modern database operations
- Configurable language filtering (default: all languages)
- Fail-fast error handling for reliable processing
- Comprehensive CLI interface
- FastAPI startup-compatible async wrapper
- Detailed progress logging and statistics
"""

import argparse
import itertools
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import text, select
from sqlalchemy.orm import Session

from config import settings
from database import Base, SessionLocal, engine
from models.text import Text, TextSegment
from parsers.perseus_xml_parser import PerseusXMLParser

logger = logging.getLogger(__name__)


@dataclass
class PopulateConfig:
    """Configuration for database population."""

    limit: Optional[int] = None
    force: bool = False
    dry_run: bool = False
    languages: List[str] = field(default_factory=list)  # Empty = all languages
    commit_batch: int = 100
    fail_fast: bool = True
    data_dir: Optional[Path] = None


@dataclass
class PopulateStats:
    """Statistics for database population operation."""

    inserted: int = 0
    skipped: int = 0
    errors: int = 0
    total_segments: int = 0
    processing_time: float = 0.0
    files_processed: int = 0


class DatabasePopulator:
    """Handles database population with batched operations and prefetched URN cache."""

    def __init__(self, config: PopulateConfig):
        self.config = config
        self.stats = PopulateStats()
        self.existing_urns = set()

    def prefetch_existing_urns(self, db: Session) -> None:
        """Prefetch all existing URNs to avoid individual database queries."""
        logger.info("Prefetching existing URNs...")
        existing_texts = db.execute(select(Text.urn)).all()
        self.existing_urns = {row.urn for row in existing_texts}
        logger.info(f"Prefetched {len(self.existing_urns)} existing URNs")

    def is_database_populated(self, db: Session) -> bool:
        """Check if the database already has texts loaded."""
        if self.existing_urns:
            return len(self.existing_urns) > 0
        return db.scalar(select(Text).limit(1)) is not None

    def clear_database(self, db: Session) -> None:
        """Clear all existing texts and segments."""
        logger.warning("Clearing existing texts and segments...")
        db.query(TextSegment).delete()
        db.query(Text).delete()
        db.commit()
        self.existing_urns.clear()  # Clear cache after clearing database

    def should_process_text(self, text_data: Dict) -> bool:
        """
        Check if text should be processed based on language filter and existing URN cache.

        Returns True if text should be processed, False if should be skipped.
        """
        # Check language filter
        if self.config.languages and text_data["language"] not in self.config.languages:
            return False

        # Check if text already exists using prefetched cache
        if text_data["urn"] in self.existing_urns:
            return False

        return True

    def prepare_batch_data(
        self, parser: PerseusXMLParser, xml_files: List[Path]
    ) -> List[Dict]:
        """
        Parse and prepare batch data for insertion.

        Returns list of text data ready for database insertion.
        """
        batch_data = []

        for xml_file in xml_files:
            try:
                text_data = parser.parse_file(xml_file)
                if not text_data:
                    logger.debug(f"Could not parse {xml_file}")
                    continue

                if self.should_process_text(text_data):
                    batch_data.append(text_data)
                    self.stats.files_processed += 1
                else:
                    self.stats.skipped += 1

            except Exception as e:
                logger.error(f"Error parsing {xml_file}: {e}")
                self.stats.errors += 1
                if self.config.fail_fast:
                    raise RuntimeError(
                        f"Failed to parse {xml_file}. Stopping due to fail_fast=True."
                    )

        return batch_data

    def insert_batch(self, db: Session, batch_data: List[Dict]) -> None:
        """
        Insert a batch of texts and their segments in a single transaction.
        Uses PostgreSQL ON CONFLICT DO NOTHING to avoid SELECT queries.
        SQLAlchemy 2.x compatible.
        """
        if not batch_data:
            return

        # Prepare values for bulk insert
        text_values = []
        for text_data in batch_data:
            text_values.append(
                {
                    "urn": text_data["urn"],
                    "author": text_data["author"],
                    "title": text_data["title"],
                    "language": text_data["language"],
                    "is_fragment": text_data["is_fragment"],
                    "text_metadata": text_data["text_metadata"],
                }
            )

        # Bulk insert texts with conflict resolution
        text_insert_sql = text("""
            INSERT INTO texts (urn, author, title, language, is_fragment, text_metadata)
            VALUES (:urn, :author, :title, :language, :is_fragment, :text_metadata)
            ON CONFLICT (urn) DO NOTHING
            RETURNING id, urn
        """)

        try:
            # Execute bulk insert with parameters
            result = db.execute(text_insert_sql, text_values)
            inserted_texts = result.all()

            # Get mapping of URN to ID for inserted texts
            urn_to_id = {row.urn: row.id for row in inserted_texts}

            # Now insert segments for successfully inserted texts only
            for text_data in batch_data:
                if text_data["urn"] in urn_to_id:
                    text_id = urn_to_id[text_data["urn"]]

                    # Create TextSegment objects for this text
                    for seg_data in text_data["segments"]:
                        segment = TextSegment(
                            text_id=text_id,
                            book=seg_data["book"],
                            line=seg_data["line"],
                            reference=seg_data["reference"],
                            content=seg_data["content"],
                            sequence=seg_data["sequence"],
                        )
                        db.add(segment)
                        self.stats.total_segments += 1

                    self.stats.inserted += 1
                    # Add to cache to avoid re-processing within the same run
                    self.existing_urns.add(text_data["urn"])
                else:
                    # Text already existed, count as skipped
                    self.stats.skipped += 1

        except Exception as e:
            logger.error(f"Error during batch insert: {e}")
            raise

    def process_file_batch(
        self, db: Session, parser: PerseusXMLParser, xml_files: List[Path]
    ) -> None:
        """
        Process a batch of XML files with a single database transaction.
        """
        try:
            # Parse and prepare all data for this batch
            batch_data = self.prepare_batch_data(parser, xml_files)

            if self.config.dry_run:
                logger.info(
                    f"DRY RUN: Would insert {len(batch_data)} texts from this batch"
                )
                for text_data in batch_data[:3]:  # Show first 3
                    logger.info(
                        f"  - {text_data['author']}: {text_data['title']} ({len(text_data['segments'])} segments)"
                    )
                return

            # Insert all data in this batch as a single transaction
            self.insert_batch(db, batch_data)

            # Commit the entire batch at once
            db.commit()
            logger.info(f"Successfully committed batch with {len(batch_data)} texts")

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            db.rollback()
            self.stats.errors += len(xml_files)  # Mark all files in batch as errors
            if self.config.fail_fast:
                raise RuntimeError(
                    f"Batch processing failed. Stopping due to fail_fast=True."
                )

    def run_population(self, db: Session) -> PopulateStats:
        """
        Main population method with batched processing and prefetched URN cache.
        SQLAlchemy 2.x compatible.

        Args:
            db: Database session

        Returns:
            PopulateStats with operation results
        """
        start_time = time.time()

        # Prefetch existing URNs for efficient duplicate checking
        self.prefetch_existing_urns(db)

        # Check if already populated
        if not self.config.force and self.is_database_populated(db):
            logger.info(
                f"Database already contains {len(self.existing_urns)} texts. Skipping population."
            )
            self.stats.skipped = len(self.existing_urns)
            return self.stats

        if self.config.force:
            self.clear_database(db)

        # Verify data directory
        data_dir = self.config.data_dir or Path(settings.assets.PERSEUS_DATA_DIR)
        if not data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")

        logger.info(f"Starting database population from {data_dir}")

        # Initialize parser
        parser = PerseusXMLParser(data_dir)
        xml_files = parser.find_all_text_files()

        if self.config.limit:
            xml_files = xml_files[: self.config.limit]
            logger.info(f"Limited to first {self.config.limit} files")

        logger.info(f"Found {len(xml_files)} XML files to process")

        # Process files in batches for better performance using itertools.batched
        batch_size = self.config.commit_batch
        total_batches = (len(xml_files) + batch_size - 1) // batch_size

        for batch_num, batch_files in enumerate(
            itertools.batched(xml_files, batch_size), start=1
        ):
            logger.info(
                f"Processing batch {batch_num}/{total_batches} ({len(batch_files)} files)..."
            )

            # Process entire batch in a single transaction
            self.process_file_batch(db, parser, list(batch_files))

        # Calculate processing time
        self.stats.processing_time = time.time() - start_time

        return self.stats


def run_population(config: PopulateConfig) -> PopulateStats:
    """
    Run database population process with given configuration.

    Args:
        config: Population configuration

    Returns:
        PopulateStats with operation results
    """
    logger.info(f"Starting population with config: {config}")

    db = SessionLocal()
    try:
        populator = DatabasePopulator(config)
        stats = populator.run_population(db)

        logger.info("Population complete!")
        logger.info(f"  Inserted: {stats.inserted} texts")
        logger.info(f"  Skipped: {stats.skipped} texts")
        logger.info(f"  Errors: {stats.errors}")
        logger.info(f"  Total segments: {stats.total_segments}")
        logger.info(f"  Processing time: {stats.processing_time:.2f} seconds")

        return stats

    finally:
        db.close()


async def populate_on_startup(config: Optional[PopulateConfig] = None) -> Dict:
    """
    Async wrapper for running population on FastAPI startup.

    This function is designed to be called from the FastAPI startup event.

    Args:
        config: Optional configuration (uses defaults if not provided)

    Returns:
        Dictionary with statistics compatible with existing startup code
    """
    if config is None:
        config = PopulateConfig()

    logger.info("Checking if database needs population...")

    # Run the synchronous population in a thread pool
    import asyncio

    loop = asyncio.get_event_loop()
    stats = await loop.run_in_executor(None, run_population, config)

    # Convert to dict for compatibility with existing startup code
    return {
        "inserted": stats.inserted,
        "skipped": stats.skipped,
        "errors": stats.errors,
        "total_segments": stats.total_segments,
        "processing_time": stats.processing_time,
        "files_processed": stats.files_processed,
    }


def main():
    """CLI interface for the database population script."""
    parser = argparse.ArgumentParser(
        description="Populate database with Perseus texts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Populate all languages
  python populate_database.py
  
  # Dry run to see what would be processed
  python populate_database.py --dry-run
  
  # Process only first 50 texts
  python populate_database.py --limit 50
  
  # Force repopulation
  python populate_database.py --force
  
  # Process only Greek texts
  python populate_database.py --languages grc
  
  # Process Greek and Latin texts
  python populate_database.py --languages grc lat
        """,
    )

    parser.add_argument(
        "--limit", type=int, help="Limit number of texts to process (for testing)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse files but don't insert into database",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Clear existing texts and repopulate (use with caution!)",
    )
    parser.add_argument(
        "--languages",
        nargs="+",
        help="Languages to process (e.g., grc lat). Default: all languages",
    )
    parser.add_argument(
        "--commit-batch",
        type=int,
        default=100,
        help="Batch size for database transactions (default: 100)",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        help="Path to Perseus data directory (uses config if not provided)",
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing on individual file errors (default: fail-fast)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create configuration
    config = PopulateConfig(
        limit=args.limit,
        dry_run=args.dry_run,
        force=args.force,
        languages=args.languages or [],
        commit_batch=args.commit_batch,
        fail_fast=not args.continue_on_error,
        data_dir=Path(args.data_dir) if args.data_dir else None,
    )

    # Safety check for force operation
    if args.force:
        response = input(
            "Are you sure you want to clear all existing texts and repopulate? (yes/no): "
        )
        if response.lower() != "yes":
            logger.info("Force operation cancelled")
            sys.exit(0)

    try:
        stats = run_population(config)
        sys.exit(0 if stats.errors == 0 else 1)
    except KeyboardInterrupt:
        logger.info("Population interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"Population failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
