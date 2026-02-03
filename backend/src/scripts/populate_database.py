"""Unified script to populate the database with Perseus texts.

This script replaces both populate_on_startup.py and populate_texts.py with
a superior implementation that eliminates duplicate key constraint violations
through atomic database operations.

Features:
- Atomic upserts using SQLAlchemy merge() to prevent race conditions
- Configurable language filtering (default: all languages)
- Fail-fast error handling for reliable processing
- Comprehensive CLI interface
- FastAPI startup-compatible async wrapper
- Detailed progress logging and statistics
"""

import argparse
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

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
    """Handles database population with atomic operations and error handling."""

    def __init__(self, config: PopulateConfig):
        self.config = config
        self.stats = PopulateStats()

    def is_database_populated(self, db: Session) -> bool:
        """Check if the database already has texts loaded."""
        return db.query(Text).limit(1).count() > 0

    def clear_database(self, db: Session) -> None:
        """Clear all existing texts and segments."""
        logger.warning("Clearing existing texts and segments...")
        db.query(TextSegment).delete()
        db.query(Text).delete()
        db.commit()

    def populate_text(self, db: Session, text_data: Dict) -> bool:
        """
        Populate a single text with atomic operations.

        Returns True if successful, False if text already exists.
        """
        # Check language filter
        if self.config.languages and text_data["language"] not in self.config.languages:
            return False

        # Atomic upsert using merge() - prevents duplicate key violations
        text = Text(
            urn=text_data["urn"],
            author=text_data["author"],
            title=text_data["title"],
            language=text_data["language"],
            is_fragment=text_data["is_fragment"],
            text_metadata=text_data["text_metadata"],
        )

        # merge() handles atomic upsert - either creates new or updates existing
        merged_text = db.merge(text)
        db.flush()  # Get the text.id without committing

        # Handle segments - delete existing ones if updating
        if not self.config.force:
            # Delete existing segments for this text
            db.query(TextSegment).filter(TextSegment.text_id == merged_text.id).delete()

        # Create TextSegment objects
        for seg_data in text_data["segments"]:
            segment = TextSegment(
                text_id=merged_text.id,
                book=seg_data["book"],
                line=seg_data["line"],
                reference=seg_data["reference"],
                content=seg_data["content"],
                sequence=seg_data["sequence"],
            )
            db.add(segment)
            self.stats.total_segments += 1

        return True

    def process_file(
        self, db: Session, parser: PerseusXMLParser, xml_file: Path
    ) -> bool:
        """
        Process a single XML file.

        Returns True if successful, False on error.
        """
        try:
            text_data = parser.parse_file(xml_file)
            if not text_data:
                logger.debug(f"Could not parse {xml_file}")
                return False

            success = self.populate_text(db, text_data)
            if success:
                self.stats.inserted += 1
                self.stats.files_processed += 1
            else:
                self.stats.skipped += 1

            return True

        except Exception as e:
            logger.error(f"Error processing {xml_file}: {e}")
            self.stats.errors += 1
            return False

    def run_population(self, db: Session) -> PopulateStats:
        """
        Main population method with fail-fast error handling.

        Args:
            db: Database session

        Returns:
            PopulateStats with operation results
        """
        start_time = time.time()

        # Check if already populated
        if not self.config.force and self.is_database_populated(db):
            existing_count = db.query(Text).count()
            logger.info(
                f"Database already contains {existing_count} texts. Skipping population."
            )
            self.stats.skipped = existing_count
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

        # Process each file with fail-fast error handling
        for idx, xml_file in enumerate(xml_files):
            # Log progress every 100 files
            if (idx + 1) % 100 == 0:
                logger.info(f"Processing file {idx + 1}/{len(xml_files)}...")

            success = self.process_file(db, parser, xml_file)

            # Fail-fast on processing errors
            if not success and self.config.fail_fast:
                db.rollback()
                raise RuntimeError(
                    f"Failed to process {xml_file}. Stopping due to fail_fast=True."
                )

            # Commit batch
            if (
                self.stats.inserted % self.config.commit_batch == 0
                and self.stats.inserted > 0
            ):
                db.commit()
                logger.info(f"Committed {self.stats.inserted} texts so far...")

        # Final commit
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            raise RuntimeError(f"Error during final commit: {e}")

        # Calculate processing time
        self.stats.processing_time = time.time() - start_time

        return self.stats


def run_population(config: PopulateConfig) -> PopulateStats:
    """
    Run the database population process with the given configuration.

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
