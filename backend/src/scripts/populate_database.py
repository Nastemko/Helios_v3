"""Unified script to populate database with Perseus texts.

This script uses CTS metadata to properly:
- Create parent LiteraryText records (one per work)
- Create LiteraryTextLangVersion records (one per language version)
- Link all versions of the same work to the same parent

Features:
- Parses __cts__.xml files for accurate metadata
- Correctly identifies translations and extracts translator names
- Two-pass approach: parent records first, then language versions
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models.text import (
    Language,
    LiteraryText,
    LiteraryTextLangVersion,
    TextSegment,
)
from parsers.cts_metadata_parser import CTSMetadataParser, VersionInfo, WorkInfo
from parsers.perseus_xml_parser import PerseusXMLParser

logger = logging.getLogger(__name__)

LANGUAGE_MAP = {
    "grc": Language.GRC,
    "lat": Language.LAT,
    "eng": Language.EN,
    "en": Language.EN,
}

# Codes present in the corpus that the Language enum cannot represent. These are
# skipped and reported rather than silently coerced to Greek (8 files: German,
# French and Italian Thucydides translations plus one Arabic Aristotle).
UNSUPPORTED_LANGUAGES = frozenset({"ger", "deu", "fre", "fra", "ita", "ara"})


@dataclass
class PopulateConfig:
    """Configuration for database population."""

    limit: Optional[int] = None
    dry_run: bool = False
    languages: List[str] = field(default_factory=list)
    commit_batch: int = 100
    fail_fast: bool = True
    data_dir: Optional[Path] = None
    failures_output: Optional[Path] = None
    rebuild: bool = False


@dataclass
class PopulateStats:
    """Statistics for database population operation."""

    inserted_works: int = 0
    inserted_versions: int = 0
    skipped: int = 0
    skipped_unsupported_language: int = 0
    errors: int = 0
    total_segments: int = 0
    processing_time: float = 0.0
    files_processed: int = 0
    failed_files: List[Path] = field(default_factory=list)


class DatabasePopulator:
    """Handles database population with CTS-aware metadata processing."""

    def __init__(self, config: PopulateConfig):
        self.config = config
        self.stats = PopulateStats()
        self.existing_version_ids = set()
        self.cts_parser: Optional[CTSMetadataParser] = None
        self.cts_data: Dict[str, WorkInfo] = {}
        self.literary_text_ids: Dict[str, int] = {}

    def prefetch_existing_version_ids(self, db: Session) -> None:
        """Prefetch all existing local_ids from LiteraryTextLangVersion."""
        logger.info("Prefetching existing version local_ids...")
        existing = db.execute(select(LiteraryTextLangVersion.local_id)).all()
        self.existing_version_ids = {row.local_id for row in existing}
        logger.info(f"Found {len(self.existing_version_ids)} existing versions")

    def is_database_populated(self, db: Session) -> bool:
        """Check if database already has texts loaded."""
        return db.scalar(select(LiteraryTextLangVersion).limit(1)) is not None

    def clear_database(self, db: Session) -> None:
        """Clear all existing texts and segments."""
        logger.warning("Clearing existing texts and segments...")
        db.query(TextSegment).delete()
        db.query(LiteraryTextLangVersion).delete()
        db.query(LiteraryText).delete()
        db.commit()
        self.existing_version_ids.clear()

    def load_cts_metadata(self) -> None:
        """Load and parse all CTS metadata files."""
        data_dir = self.config.data_dir or Path(settings.assets.PERSEUS_DATA_DIR)
        logger.info(f"Loading CTS metadata from {data_dir}...")

        self.cts_parser = CTSMetadataParser(data_dir)
        self.cts_data = self.cts_parser.parse_all()

        logger.info(f"Loaded {len(self.cts_data)} works from CTS metadata")

        total_versions = sum(len(w.versions) for w in self.cts_data.values())
        logger.info(f"Found {total_versions} total versions")

        translations = sum(
            1
            for w in self.cts_data.values()
            for v in w.versions
            if v.translator is not None
        )
        logger.info(f"Found {translations} translations")

    def create_parent_records(self, db: Session) -> Dict[str, int]:
        """
        Create LiteraryText parent records for all works in CTS data.

        Returns:
            Dictionary mapping work_local_id to database ID
        """
        logger.info("Creating LiteraryText parent records...")

        existing = db.execute(select(LiteraryText.local_id, LiteraryText.id)).all()
        id_map = {row.local_id: row.id for row in existing}

        new_parents = []
        for work_local_id, work_info in self.cts_data.items():
            if work_local_id not in id_map:
                new_parents.append(
                    {
                        "local_id": work_local_id,
                    }
                )

        if new_parents:
            stmt = (
                insert(LiteraryText)
                .values(new_parents)
                .on_conflict_do_nothing(index_elements=["local_id"])
                .returning(LiteraryText.id, LiteraryText.local_id)
            )
            result = db.execute(stmt)
            inserted = result.fetchall()
            for row in inserted:
                id_map[row.local_id] = row.id
            db.commit()
            # Count rows actually returned, not rows attempted: on_conflict_do_nothing
            # means some of new_parents may not have been inserted.
            self.stats.inserted_works = len(inserted)

        logger.info(f"Total parent records: {len(id_map)}")
        return id_map

    def should_process_version(self, local_id: str, language: str) -> bool:
        """Check if version should be processed."""
        if self.config.languages and language not in self.config.languages:
            return False
        if local_id in self.existing_version_ids:
            return False
        return True

    def insert_version(
        self,
        db: Session,
        text_data: Dict,
        version_info: Optional[VersionInfo],
        parent_id: int,
    ) -> None:
        """
        Insert a single LiteraryTextLangVersion and its segments.

        Returns:
            The new version ID or None if skipped
        """
        local_id = text_data["local_id"]

        language = "grc"
        translator = None
        author = "Unknown"
        title = "Unknown"

        if version_info:
            language = version_info.language
            translator = version_info.translator
            author = version_info.author
            title = version_info.title
        else:
            language = text_data.get("language", "grc")
            author = text_data.get("author", "Unknown")
            title = text_data.get("title", "Unknown")
            if language not in ["grc", "lat"]:
                translator = "unknown"

        lang_enum = LANGUAGE_MAP.get(language, Language.GRC)

        version = LiteraryTextLangVersion(
            local_id=local_id,
            literary_text_id=parent_id,
            language=lang_enum,
            author=author,
            title=title,
            translator=translator,
        )
        db.add(version)
        db.flush()

        for seg_data in text_data["segments"]:
            segment = TextSegment(
                lang_version_id=version.id,
                book=seg_data["book"],
                line=seg_data["line"],
                reference=seg_data["reference"],
                content=seg_data["content"],
                sequence=seg_data["sequence"],
            )
            db.add(segment)
            self.stats.total_segments += 1

        self.stats.inserted_versions += 1

    def run_population(self, db: Session) -> PopulateStats:
        """
        Main population method with CTS-aware processing.

        Already-processed versions are skipped via should_process_version, so
        this method is safe to run on every startup — it resumes where it left off.

        Args:
            db: Database session

        Returns:
            PopulateStats with operation results
        """
        start_time = time.time()

        if self.config.rebuild and not self.config.dry_run:
            logger.warning("--rebuild requested: clearing existing texts and segments")
            self.clear_database(db)

        self.prefetch_existing_version_ids(db)

        if self.config.dry_run:
            logger.info("Dry run mode — skipping actual population.")

        data_dir = self.config.data_dir or Path(settings.assets.PERSEUS_DATA_DIR)
        if not data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")

        logger.info(f"Starting database population from {data_dir}")

        self.load_cts_metadata()

        parent_ids = self.create_parent_records(db)
        self.literary_text_ids = parent_ids

        parser = PerseusXMLParser(data_dir)
        xml_files = parser.find_all_text_files()

        if self.config.limit:
            xml_files = xml_files[: self.config.limit]
            logger.info(f"Limited to first {self.config.limit} files")

        logger.info(f"Processing {len(xml_files)} XML files...")

        batch_count = 0
        for xml_file in xml_files:
            work_local_id = ""
            try:
                text_data = parser.parse_file(xml_file)
                if not text_data:
                    self.stats.failed_files.append(xml_file)
                    continue

                local_id = text_data["local_id"]

                if not self.should_process_version(
                    local_id, text_data.get("language", "grc")
                ):
                    self.stats.skipped += 1
                    continue

                if self.config.dry_run:
                    logger.info(f"DRY RUN: Would insert {local_id}")
                    continue

                version_info = None
                if self.cts_parser:
                    version_info = self.cts_parser.get_version_info(local_id)

                language = (
                    version_info.language
                    if version_info
                    else text_data.get("language", "grc")
                )
                if language in UNSUPPORTED_LANGUAGES or language not in LANGUAGE_MAP:
                    logger.warning(
                        "Skipping %s: language '%s' has no Language enum member",
                        local_id,
                        language,
                    )
                    self.stats.skipped_unsupported_language += 1
                    continue

                work_local_id = ".".join(local_id.split(".")[:2])

                # A SAVEPOINT per file: a failure rolls back only this version,
                # leaving the session usable so the rest of the batch survives.
                with db.begin_nested():
                    parent_id = parent_ids.get(work_local_id)

                    if not parent_id:
                        logger.debug(f"Creating parent record for {work_local_id}")
                        new_parent = LiteraryText(
                            local_id=work_local_id,
                        )
                        db.add(new_parent)
                        db.flush()
                        db.refresh(new_parent, ["id"])
                        parent_id: int = new_parent.id  # type: ignore[assignment]
                        parent_ids[work_local_id] = parent_id
                        self.stats.inserted_works += 1

                    assert parent_id is not None
                    self.insert_version(db, text_data, version_info, parent_id)

                self.stats.files_processed += 1
                batch_count += 1

                if batch_count >= self.config.commit_batch:
                    db.commit()
                    logger.info(
                        f"Committed batch: {self.stats.inserted_versions} versions, "
                        f"{self.stats.total_segments} segments"
                    )
                    batch_count = 0

            except Exception as e:
                logger.error(
                    "Error processing %s: %s: %s", xml_file, type(e).__name__, e
                )
                self.stats.errors += 1
                self.stats.failed_files.append(xml_file)
                # The savepoint rolled back, so any parent inserted inside it is
                # gone; drop the cached id to avoid handing out a stale FK.
                parent_ids.pop(work_local_id, None)
                if self.config.fail_fast:
                    db.rollback()
                    raise

        if batch_count > 0:
            db.commit()

        self.stats.processing_time = time.time() - start_time

        if self.stats.failed_files and self.config.failures_output:
            out_path = self.config.failures_output
            payload = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "data_dir": str(data_dir),
                "failed_files": [str(p.resolve()) for p in self.stats.failed_files],
            }
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            logger.info(
                "Wrote %d failed file paths to %s",
                len(self.stats.failed_files),
                out_path,
            )

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
        logger.info(f"  Works inserted: {stats.inserted_works}")
        logger.info(f"  Versions inserted: {stats.inserted_versions}")
        logger.info(f"  Skipped: {stats.skipped}")
        logger.info(
            f"  Skipped (unsupported language): {stats.skipped_unsupported_language}"
        )
        logger.info(f"  Errors: {stats.errors}")
        logger.info(f"  Total segments: {stats.total_segments}")
        logger.info(f"  Processing time: {stats.processing_time:.2f} seconds")

        return stats

    finally:
        db.close()


async def populate_on_startup(config: Optional[PopulateConfig] = None) -> Dict:
    """
    Async wrapper for running population on FastAPI startup.

    Args:
        config: Optional configuration

    Returns:
        Dictionary with statistics
    """
    if config is None:
        data_dir = Path(settings.assets.PERSEUS_DATA_DIR)
        failures_output = data_dir.parent / "lxml_failures.json"
        config = PopulateConfig(fail_fast=False, failures_output=failures_output)

    logger.info("Checking if database needs population...")

    import asyncio

    loop = asyncio.get_event_loop()
    stats = await loop.run_in_executor(None, run_population, config)

    return {
        "inserted_works": stats.inserted_works,
        "inserted_versions": stats.inserted_versions,
        "skipped": stats.skipped,
        "skipped_unsupported_language": stats.skipped_unsupported_language,
        "errors": stats.errors,
        "total_segments": stats.total_segments,
        "processing_time": stats.processing_time,
        "files_processed": stats.files_processed,
        "failed_files": [str(p) for p in stats.failed_files],
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Populate database with Perseus texts")
    ap.add_argument("--limit", type=int, help="Limit number of files to process")
    ap.add_argument("--dry-run", action="store_true", help="Show what would be done")
    ap.add_argument(
        "--languages",
        nargs="*",
        default=[],
        help="Filter by language codes (grc, lat, en)",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Commit batch size",
    )
    ap.add_argument(
        "--fail-fast",
        action="store_true",
        default=True,
        help="Stop on first error",
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        help="Override data directory",
    )
    ap.add_argument(
        "--rebuild",
        action="store_true",
        help=(
            "Delete all existing texts, versions and segments before loading. "
            "Use this once after fixing the parsers to clear duplicated segments "
            "written by earlier runs. Never triggered on startup."
        ),
    )
    ap.add_argument(
        "--failures-output",
        type=Path,
        default=None,
        help=(
            "Path to write a JSON list of files where lxml parsing failed "
            "(consumed by populate_database_llm.py --from-failures-file). "
            "Defaults to <data-dir>/../lxml_failures.json when omitted."
        ),
    )

    args = ap.parse_args()

    failures_output = args.failures_output
    if failures_output is None and args.data_dir is not None:
        failures_output = args.data_dir.parent / "lxml_failures.json"

    config = PopulateConfig(
        limit=args.limit,
        dry_run=args.dry_run,
        languages=args.languages,
        commit_batch=args.batch_size,
        fail_fast=args.fail_fast,
        data_dir=args.data_dir,
        failures_output=failures_output,
        rebuild=args.rebuild,
    )

    stats = run_population(config)
    sys.exit(0 if stats.errors == 0 else 1)
