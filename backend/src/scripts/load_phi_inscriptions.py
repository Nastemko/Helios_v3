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
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models.inscription import Inscription, InscriptionSegment

logger = logging.getLogger(__name__)

# Data validation and canonicalization functions (moved from data_utils.py)


def canonicalize_region_name(region: Optional[str]) -> Optional[str]:
    """
    Canonicalize region names: trim whitespace, proper capitalization, preserve acronyms.

    Accepts None safely and returns None for non-string inputs.

    Examples:
        "  attica (ig i-iii)  " → "Attica (IG I-III)"
        "athens: agora" → "Athens: Agora"
        "" → None
    """
    if not region or not isinstance(region, str):
        return None

    # Trim whitespace
    canonical = region.strip()

    # Convert to title case, but preserve geographical terms
    canonical = canonical.title()

    # Handle geographical and archaeological terms properly
    # Preserve acronyms like IG, SEG, etc.
    acronyms = [
        "IG",
        "SEG",
        "I",
        "II",
        "III",
        "IV",
        "V",
        "VI",
        "VII",
        "VIII",
        "IX",
        "X",
    ]

    for acronym in acronyms:
        canonical = canonical.replace(f"({acronym.lower()} ", f"({acronym}) ")

    return canonical if canonical else None


def parse_date_value(date_val: Optional[object]) -> Optional[int]:
    """
    Parse date value with None fallback for invalid values.

    BC dates should remain negative, AD dates positive.

    Examples:
        "-350" → -350 (350 BC)
        "100" → 100 (100 AD)
        None → None
    """
    if date_val is None:
        return None

    try:
        return int(str(date_val).strip())
    except (ValueError, TypeError):
        return None


def validate_inscription_data(inscription: dict) -> dict:
    """
    Validate and canonicalize inscription data for loading.

    Returns dictionary with validated and canonicalized data.
    """
    return {
        "region_main": canonicalize_region_name(inscription.get("region_main")),
        "region_sub": canonicalize_region_name(inscription.get("region_sub")),
        "date_min": parse_date_value(inscription.get("date_min")),
        "date_max": parse_date_value(inscription.get("date_max")),
    }


# PHI fields promoted to their own columns; per the Inscription model these are
# deliberately NOT duplicated into metadata_raw. `text` is excluded too — it is
# split into InscriptionSegment rows.
_EXTRACTED_PHI_FIELDS = frozenset(
    {
        "id",
        "text",
        "region_main",
        "region_sub",
        "date_min",
        "date_max",
        "date_str",
        "date_circa",
    }
)


def extract_residual_metadata(inscription: dict) -> Optional[dict]:
    """Return the PHI fields that have no dedicated column, or None if empty.

    PHI records are flat — there is no nested "metadata" key — so reading
    `inscription.get("metadata")` always yielded None and silently dropped
    `partner_link`, `ids_alt`, and any other unmapped field.
    """
    residual = {
        key: value
        for key, value in inscription.items()
        if key not in _EXTRACTED_PHI_FIELDS
    }
    return residual or None


@dataclass
class PHIConfig:
    """Configuration for PHI inscription loading."""

    phi_json_path: Optional[str] = None
    limit: Optional[int] = None
    dry_run: bool = False
    batch_size: int = 500
    fail_fast: bool = True


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
    """Handles PHI inscription loading with batched operations and optimized local_id cache."""

    def __init__(self, config: PHIConfig):
        self.config = config
        self.stats = PHIStats()
        self.existing_phi_ids = set()

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

    def prefetch_existing_phi_ids(self, db: Session) -> None:
        """Prefetch existing PHI phi_ids to avoid individual database queries."""
        logger.info("Prefetching existing PHI phi_ids...")

        # Fetch all PHI inscription phi_ids
        existing_phi = db.execute(select(Inscription.phi_id).distinct()).all()

        self.existing_phi_ids = {row.phi_id for row in existing_phi}
        logger.info(f"Prefetched {len(self.existing_phi_ids)} existing PHI phi_ids")

    def is_database_populated_with_phi(self, db: Session) -> bool:
        """Check if database already has PHI inscriptions."""
        if self.existing_phi_ids:
            return len(self.existing_phi_ids) > 0
        result = db.scalar(select(func.count(Inscription.id)).limit(1))
        return result is not None and result > 0

    def should_process_inscription(self, inscription: Dict) -> bool:
        """Check if inscription should be processed based on existing phi_id cache."""
        phi_id = inscription.get("id")
        if not phi_id:
            return False

        return phi_id not in self.existing_phi_ids

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

    def create_segments_for_inscription(
        self, db: Session, inscription: Dict, inscription_id: int
    ) -> None:
        """Create inscription segments."""
        content = inscription.get("text", "").strip()

        if not content:
            return

        # Split on periods to create segments, keeping reasonable chunks
        sentences = [s.strip() for s in content.split(".") if s.strip()]

        if sentences:
            for seq, sentence in enumerate(sentences, 1):
                segment = InscriptionSegment(
                    inscription_id=inscription_id,
                    sequence=seq,
                    content=sentence,
                )
                # TODO: Is it done in a transaction?
                db.add(segment)
                self.stats.total_segments += 1
        else:
            # Single segment for whole inscription if no periods
            segment = InscriptionSegment(
                inscription_id=inscription_id,
                sequence=1,
                content=content,
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

            # Validate and canonicalize inscription data
            validated_data = validate_inscription_data(inscription)

            # Build title using canonicalized region names
            title = f"PHI {phi_id}"
            if validated_data["region_sub"]:
                title = f"{validated_data['region_sub']} - PHI {phi_id}"
            elif validated_data["region_main"]:
                title = f"{validated_data['region_main']} - PHI {phi_id}"

            inscription_values.append(
                {
                    "phi_id": phi_id,  # Integer, not string
                    "title": title,
                    "region_main": validated_data["region_main"],
                    "region_sub": validated_data["region_sub"],
                    "date_min": validated_data["date_min"],
                    "date_max": validated_data["date_max"],
                    "date_str": inscription.get("date_str"),  # Dedicated column
                    "date_circa": inscription.get(
                        "date_circa", False
                    ),  # Dedicated column
                    "metadata_raw": extract_residual_metadata(inscription),
                }
            )

        # Use SQLAlchemy's PostgreSQL insert() dialect
        stmt = (
            insert(Inscription)
            .values(inscription_values)
            .on_conflict_do_nothing(index_elements=["phi_id"])
            .returning(Inscription.id, Inscription.phi_id)
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

            # Get mapping of phi_id to ID for inserted inscriptions
            phi_id_to_id = {row.phi_id: row.id for row in inserted_texts}

            # Create segments for successfully inserted inscriptions
            for inscription in batch_data:
                phi_id = inscription.get("id")

                if phi_id in phi_id_to_id:
                    inscription_id = phi_id_to_id[phi_id]
                    self.create_segments_for_inscription(
                        db, inscription, inscription_id
                    )
                    self.stats.inserted += 1
                    self.existing_phi_ids.add(phi_id)
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

        # Prefetch existing phi_ids
        self.prefetch_existing_phi_ids(db)

        # Check if already populated
        if self.is_database_populated_with_phi(db):
            logger.info(
                f"Database already contains {len(self.existing_phi_ids)} PHI inscriptions. Skipping loading."
            )
            self.stats.skipped = len(self.existing_phi_ids)
            return self.stats

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
        total_inscriptions = db.scalar(select(func.count(Inscription.id)))
        total_segments = db.scalar(select(func.count(InscriptionSegment.id)))

        logger.info("=" * 50)
        logger.info("Database totals:")
        logger.info(f"  Total inscriptions: {total_inscriptions}")
        logger.info(f"  Total segments: {total_segments}")

        return stats

    except Exception as e:
        logger.error(f"Fatal error during import: {e}")
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
