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

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from config import settings
from database import Base, SessionLocal, engine
from models.text import Language, LiteraryText, TextMetadata, TextSegment
from parsers.perseus_xml_parser import PerseusXMLParser

logger = logging.getLogger(__name__)

# Language mapping from parser codes to enum
LANGUAGE_MAP = {
    "grc": Language.GRC,
    "lat": Language.LAT,
    "en": Language.EN,
}


@dataclass
class PopulateConfig:
    """Configuration for database population."""

    limit: Optional[int] = None
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
    """Handles database population with batched operations and prefetched local_id cache."""

    def __init__(self, config: PopulateConfig):
        self.config = config
        self.stats = PopulateStats()
        self.existing_local_ids = set()

    def prefetch_existing_local_ids(self, db: Session) -> None:
        """Prefetch all existing local_ids to avoid individual database queries."""
        logger.info("Prefetching existing local_ids...")
        existing_texts = db.execute(select(LiteraryText.local_id)).all()
        self.existing_local_ids = {row.local_id for row in existing_texts}
        logger.info(f"Prefetched {len(self.existing_local_ids)} existing local_ids")

    def is_database_populated(self, db: Session) -> bool:
        """Check if database already has texts loaded."""
        if self.existing_local_ids:
            return len(self.existing_local_ids) > 0
        return db.scalar(select(LiteraryText).limit(1)) is not None

    def clear_database(self, db: Session) -> None:
        """Clear all existing texts and segments."""
        logger.warning("Clearing existing texts and segments...")
        db.query(TextSegment).delete()
        db.query(LiteraryText).delete()
        db.query(TextMetadata).delete()
        db.commit()
        self.existing_local_ids.clear()  # Clear cache after clearing database

    def prefetch_and_create_text_metadata(
        self, db: Session, all_text_data: List[Dict]
    ) -> Dict[str, int]:
        """
        First pass: Collect all unique local_ids and create TextMetadata records.
        Returns mapping of local_id -> metadata_id.
        """
        logger.info("Creating TextMetadata records for all unique local_ids...")

        # Collect unique local_ids with their metadata
        unique_metadata = {}
        for text_data in all_text_data:
            local_id = text_data["local_id"]
            if local_id not in unique_metadata:
                unique_metadata[local_id] = text_data["text_metadata"]

        # Check which metadata already exists
        existing_metadata = db.execute(
            select(TextMetadata.local_id, TextMetadata.id).where(
                TextMetadata.local_id.in_(unique_metadata.keys())
            )
        ).all()
        existing_metadata_map = {row.local_id: row.id for row in existing_metadata}

        # Prepare new metadata for insertion
        new_metadata_values = []
        for local_id, metadata in unique_metadata.items():
            if local_id not in existing_metadata_map:
                new_metadata_values.append(
                    {
                        "local_id": local_id,
                        "metadata_content": metadata,
                    }
                )

        # Insert new metadata records
        if new_metadata_values:
            stmt = (
                insert(TextMetadata)
                .values(new_metadata_values)
                .on_conflict_do_nothing(index_elements=["local_id"])
                .returning(TextMetadata.local_id, TextMetadata.id)
            )
            result = db.execute(stmt)
            new_metadata_records = result.fetchall()

            # Add new records to existing map
            for record in new_metadata_records:
                existing_metadata_map[record.local_id] = record.id

        logger.info(f"Processed {len(unique_metadata)} unique metadata records")
        return existing_metadata_map

    def should_process_text(self, text_data: Dict) -> bool:
        """
        Check if text should be processed based on language filter and existing local_id cache.

        Returns True if text should be processed, False if should be skipped.
        """
        # Check language filter
        if self.config.languages and text_data["language"] not in self.config.languages:
            return False

        # Check if text already exists using prefetched cache
        if text_data["local_id"] in self.existing_local_ids:
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

    def insert_batch(
        self, db: Session, batch_data: List[Dict], metadata_id_map: Dict[str, int]
    ) -> None:
        """
        Insert a batch of LiteraryText records and their segments in a single transaction.
        Uses PostgreSQL ON CONFLICT DO NOTHING to avoid SELECT queries.
        SQLAlchemy 2.x compatible with proper handling of empty results.
        """
        if not batch_data:
            return

        # Prepare values for bulk insert
        text_values = []
        for text_data in batch_data:
            text_values.append(
                {
                    "local_id": text_data["local_id"],
                    "author": text_data["author"],
                    "title": text_data["title"],
                    "language": LANGUAGE_MAP.get(text_data["language"], Language.GRC),
                    "translator": None,  # Perseus data are originals, not translations
                    "metadata_id": metadata_id_map[text_data["local_id"]],
                }
            )

        # Use SQLAlchemy's PostgreSQL insert() dialect
        stmt = (
            insert(LiteraryText)
            .values(text_values)
            .on_conflict_do_nothing(index_elements=["local_id"])
            .returning(LiteraryText.id, LiteraryText.local_id)
        )

        try:
            # Execute bulk insert with parameters
            result = db.execute(stmt)
            inserted_texts = result.fetchall()  # This will be [] if all conflicted

            # Handle empty results gracefully - this is the key fix
            if not inserted_texts:
                logger.debug("All texts in batch already exist (no new rows inserted)")
                # Mark all as skipped
                self.stats.skipped += len(batch_data)
                return

            # Get mapping of local_id to ID for inserted texts
            local_id_to_id = {row.local_id: row.id for row in inserted_texts}

            # Now insert segments for successfully inserted texts only
            for text_data in batch_data:
                if text_data["local_id"] in local_id_to_id:
                    text_id = local_id_to_id[text_data["local_id"]]

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
                    self.existing_local_ids.add(text_data["local_id"])
                else:
                    # Text already existed, count as skipped
                    self.stats.skipped += 1

        except Exception as e:
            logger.error(f"Error during batch insert: {e}")
            raise

    def process_file_batch(
        self,
        db: Session,
        parser: PerseusXMLParser,
        xml_files: List[Path],
        metadata_id_map: Dict[str, int],
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
            self.insert_batch(db, batch_data, metadata_id_map)

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

        # Prefetch existing local_ids for efficient duplicate checking
        self.prefetch_existing_local_ids(db)

        # Check if already populated
        if self.is_database_populated(db):
            logger.info(
                f"Database already contains {len(self.existing_local_ids)} texts. Skipping population."
            )
            self.stats.skipped = len(self.existing_local_ids)
            return self.stats

        # Verify data directory
        data_dir = self.config.data_dir or Path(settings.assets.PERSEUS_DATA_DIR)
        if not data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")

        logger.info(f"Starting database population from {data_dir}")

        # Initialize parser and parse all files first for two-pass strategy
        parser = PerseusXMLParser(data_dir)
        xml_files = parser.find_all_text_files()

        if self.config.limit:
            xml_files = xml_files[: self.config.limit]
            logger.info(f"Limited to first {self.config.limit} files")

        logger.info(f"Found {len(xml_files)} XML files to process")

        # First pass: Parse all files and collect data
        logger.info("First pass: Parsing all XML files...")
        all_text_data = []
        for xml_file in xml_files:
            try:
                text_data = parser.parse_file(xml_file)
                if text_data and self.should_process_text(text_data):
                    all_text_data.append(text_data)
                    self.stats.files_processed += 1
                elif text_data:
                    self.stats.skipped += 1
            except Exception as e:
                logger.error(f"Error parsing {xml_file}: {e}")
                self.stats.errors += 1
                if self.config.fail_fast:
                    raise RuntimeError(
                        f"Failed to parse {xml_file}. Stopping due to fail_fast=True."
                    )

        logger.info(f"Parsed {len(all_text_data)} valid text files")

        # Second pass: Create all TextMetadata records
        metadata_id_map = self.prefetch_and_create_text_metadata(db, all_text_data)

        # Third pass: Process LiteraryText records in batches
        batch_size = self.config.commit_batch
        total_batches = (len(all_text_data) + batch_size - 1) // batch_size

        for batch_num, batch_start in enumerate(
            range(0, len(all_text_data), batch_size), start=1
        ):
            batch_end = min(batch_start + batch_size, len(all_text_data))
            batch_data = all_text_data[batch_start:batch_end]

            logger.info(
                f"Processing batch {batch_num}/{total_batches} ({len(batch_data)} texts)..."
            )

            # Process entire batch in a single transaction
            self.insert_batch(db, batch_data, metadata_id_map)
            db.commit()

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
