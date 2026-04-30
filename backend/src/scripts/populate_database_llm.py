"""LLM-based database populator for Perseus literary texts.

Uses the OpenAI SDK pointed at OpenRouter (free models) to extract structured
text data directly from Perseus TEI XML files and insert it into the database.

This is an LLM-powered alternative to the lxml-based populate_database.py script.
The LLM reads raw XML and returns structured JSON with metadata and text segments.

Usage:
    PYTHONPATH=./src python src/scripts/populate_database_llm.py --limit 5 --dry-run
    PYTHONPATH=./src python src/scripts/populate_database_llm.py --model google/gemma-2-9b-it:free
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from openai import OpenAI
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from database import SessionLocal
from models.text import Language, LiteraryText, LiteraryTextLangVersion, TextSegment


class OpenRouterConfig(BaseSettings):
    """OpenRouter LLM settings — bespoke to this script. Reads OPENROUTER_* env."""

    API_KEY: str = ""
    BASE_URL: str = "https://openrouter.ai/api/v1"
    MODEL: str = "meta-llama/llama-3.1-8b-instruct:free"
    TEMPERATURE: float = 0.1
    MAX_TOKENS: int = 4096

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_prefix="OPENROUTER_",
    )


openrouter_config = OpenRouterConfig()

logger = logging.getLogger(__name__)

LANGUAGE_MAP = {
    "grc": Language.GRC,
    "lat": Language.LAT,
    "eng": Language.EN,
    "en": Language.EN,
}

# Maximum characters of XML to send per LLM call. Free models typically have
# 32k–128k token context windows, but smaller chunks produce more reliable JSON.
HEADER_CHUNK_MAX = 4_000
BODY_CHUNK_MAX = 6_000


# ---------------------------------------------------------------------------
# Configuration / stats
# ---------------------------------------------------------------------------


@dataclass
class LLMPopulateConfig:
    """Configuration for the LLM-based database population."""

    limit: Optional[int] = None
    dry_run: bool = False
    languages: List[str] = field(default_factory=list)
    commit_batch: int = 50
    fail_fast: bool = False
    data_dir: Optional[Path] = None
    model: Optional[str] = None
    from_failures_file: Optional[Path] = None


@dataclass
class LLMPopulateStats:
    """Running statistics for the population run."""

    inserted_works: int = 0
    inserted_versions: int = 0
    skipped: int = 0
    errors: int = 0
    total_segments: int = 0
    llm_calls: int = 0
    processing_time: float = 0.0
    files_processed: int = 0


# ---------------------------------------------------------------------------
# XML chunker — pure-string splitting, no lxml required
# ---------------------------------------------------------------------------


class XMLChunker:
    """Splits a raw TEI XML string into a header chunk and body chunks.

    Avoids any XML parsing — we just need the raw text sections so the LLM
    can read them. This keeps dependencies minimal and handles malformed XML.
    """

    # Patterns are intentionally simple; TEI files are well-formed enough.
    _HEADER_RE = re.compile(
        r"<teiHeader\b.*?</teiHeader>", re.DOTALL | re.IGNORECASE
    )
    _BODY_RE = re.compile(r"<body\b.*?</body>", re.DOTALL | re.IGNORECASE)

    def __init__(self, xml_text: str):
        self.xml_text = xml_text

    @classmethod
    def from_file(cls, path: Path) -> "XMLChunker":
        text = path.read_text(encoding="utf-8", errors="replace")
        return cls(text)

    def header_chunk(self) -> str:
        """Return the <teiHeader> section, truncated to HEADER_CHUNK_MAX chars."""
        match = self._HEADER_RE.search(self.xml_text)
        if match:
            return match.group(0)[:HEADER_CHUNK_MAX]
        # Fallback: return the first HEADER_CHUNK_MAX chars of the whole file
        return self.xml_text[:HEADER_CHUNK_MAX]

    def body_chunks(self) -> List[str]:
        """Return the <body> content split into ≤BODY_CHUNK_MAX-char pieces."""
        match = self._BODY_RE.search(self.xml_text)
        body = match.group(0) if match else self.xml_text
        chunks = []
        for start in range(0, len(body), BODY_CHUNK_MAX):
            chunks.append(body[start : start + BODY_CHUNK_MAX])
        return chunks or [body[:BODY_CHUNK_MAX]]

    def filename_local_id(self, xml_path: Path) -> str:
        """Derive a best-effort local_id from the file path as fallback."""
        stem = xml_path.stem
        if ".perseus-" in stem:
            return stem
        return stem


# ---------------------------------------------------------------------------
# LLM XML parser — calls OpenRouter via the OpenAI SDK
# ---------------------------------------------------------------------------

_METADATA_SYSTEM = """\
You are a data-extraction assistant specialising in Perseus Digital Library TEI XML.
Given a <teiHeader> XML snippet, extract the following fields and return ONLY a JSON object.
Do not include any prose, markdown, or code fences — just raw JSON.

Required JSON schema:
{
  "local_id": "<string: CTS URN suffix, e.g. tlg0013.tlg001.perseus-grc2 — derive from refsDecl, idno[@type='filename'], or the div[@type='edition']/@n attribute>",
  "author":   "<string: author name, 'Unknown' if not present>",
  "title":    "<string: work title, 'Unknown' if not present>",
  "language": "<string: language code — 'grc' for Greek, 'lat' for Latin, 'en'/'eng' for English>",
  "translator": "<string | null: translator name if this is a translation, otherwise null>"
}
"""

_SEGMENTS_SYSTEM = """\
You are a data-extraction assistant specialising in Perseus Digital Library TEI XML.
Given a fragment of a TEI <body> element, extract every text segment (line or paragraph)
and return ONLY a JSON array. Do not include any prose, markdown, or code fences — just raw JSON.

Each element in the array must follow this schema:
{
  "book":      "<string: book/section number from the enclosing div[@type='textpart']/@n, or '' if absent>",
  "line":      "<string: line number from <l>/@n or paragraph index, or ''>",
  "reference": "<string: canonical reference, e.g. '1.5' for book 1 line 5, or just the line number>",
  "content":   "<string: the plain text content of the line or paragraph, with all XML tags stripped>"
}

Rules:
- Preserve the original Greek/Latin/English text exactly (Unicode characters included).
- Strip all XML tags; keep only text content.
- Omit segments with empty or whitespace-only content.
- Do NOT add a 'sequence' field — it will be assigned by the caller.
"""


class LLMXMLParser:
    """Extracts structured data from Perseus TEI XML using an OpenRouter LLM."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.model = model or openrouter_config.MODEL
        self.temperature = temperature if temperature is not None else openrouter_config.TEMPERATURE
        self.max_tokens = max_tokens or openrouter_config.MAX_TOKENS
        self.client = OpenAI(
            api_key=api_key or openrouter_config.API_KEY,
            base_url=base_url or openrouter_config.BASE_URL,
        )
        self._call_count = 0

    def _chat(self, system: str, user_content: str) -> str:
        """Send a chat completion request and return the raw response string."""
        self._call_count += 1
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
        )
        return (response.choices[0].message.content or "").strip()

    @staticmethod
    def _strip_fences(text: str) -> str:
        """Remove markdown code fences if the model wrapped the JSON."""
        text = text.strip()
        fence = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.DOTALL | re.IGNORECASE)
        m = fence.match(text)
        if m:
            return m.group(1).strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
        return text

    def extract_metadata(self, header_chunk: str, fallback_local_id: str) -> Dict:
        """Call the LLM to extract metadata from the teiHeader section."""
        raw = self._chat(_METADATA_SYSTEM, header_chunk)
        cleaned = self._strip_fences(raw)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            logger.warning("Metadata JSON parse failed; using fallback values")
            data = {}

        return {
            "local_id": data.get("local_id") or fallback_local_id,
            "author": data.get("author") or "Unknown",
            "title": data.get("title") or "Unknown",
            "language": data.get("language") or "grc",
            "translator": data.get("translator") or None,
        }

    def extract_segments(
        self, body_chunks: List[str]
    ) -> List[Dict]:
        """Call the LLM for each body chunk and aggregate segments."""
        all_segments: List[Dict] = []
        sequence = 0

        for chunk_idx, chunk in enumerate(body_chunks):
            logger.debug("Extracting segments from body chunk %d", chunk_idx + 1)
            raw = self._chat(_SEGMENTS_SYSTEM, chunk)
            cleaned = self._strip_fences(raw)

            try:
                items = json.loads(cleaned)
                if not isinstance(items, list):
                    logger.warning("Segment response is not a list in chunk %d", chunk_idx)
                    continue
            except json.JSONDecodeError:
                logger.warning("Segment JSON parse failed for chunk %d", chunk_idx)
                continue

            for item in items:
                if not isinstance(item, dict):
                    continue
                content = str(item.get("content", "")).strip()
                if not content:
                    continue
                all_segments.append(
                    {
                        "book": str(item.get("book", "")),
                        "line": str(item.get("line", "")),
                        "reference": str(item.get("reference", str(sequence))),
                        "content": content,
                        "sequence": sequence,
                    }
                )
                sequence += 1

        return all_segments

    def parse_file(self, xml_path: Path) -> Optional[Dict]:
        """Parse a single XML file using the LLM. Returns structured text data or None."""
        chunker = XMLChunker.from_file(xml_path)
        fallback_id = chunker.filename_local_id(xml_path)

        logger.debug("Extracting metadata from %s", xml_path.name)
        metadata = self.extract_metadata(chunker.header_chunk(), fallback_id)

        logger.debug("Extracting segments from %s", xml_path.name)
        segments = self.extract_segments(chunker.body_chunks())

        if not segments:
            logger.warning("No segments extracted from %s", xml_path.name)
            return None

        return {
            "local_id": metadata["local_id"],
            "author": metadata["author"],
            "title": metadata["title"],
            "language": metadata["language"],
            "translator": metadata["translator"],
            "segments": segments,
        }


# ---------------------------------------------------------------------------
# Database populator
# ---------------------------------------------------------------------------


class LLMDatabasePopulator:
    """Orchestrates LLM parsing and database insertion for Perseus XML files."""

    def __init__(self, config: LLMPopulateConfig) -> None:
        self.config = config
        self.stats = LLMPopulateStats()
        self.existing_version_ids: set[str] = set()
        self.literary_text_ids: Dict[str, int] = {}
        self.llm_parser: Optional[LLMXMLParser] = None

    def _init_llm_parser(self) -> None:
        self.llm_parser = LLMXMLParser(model=self.config.model)
        logger.info("Initialised LLMXMLParser with model: %s", self.llm_parser.model)

    def _prefetch_existing_version_ids(self, db: Session) -> None:
        existing = db.execute(select(LiteraryTextLangVersion.local_id)).all()
        self.existing_version_ids = {row.local_id for row in existing}
        logger.info("Found %d existing versions in DB", len(self.existing_version_ids))

    def _should_process(self, local_id: str, language: str) -> bool:
        if self.config.languages and language not in self.config.languages:
            return False
        if local_id in self.existing_version_ids:
            return False
        return True

    def _ensure_parent_record(self, db: Session, work_local_id: str) -> int:
        """Return the DB id for the LiteraryText parent, creating it if needed."""
        if work_local_id in self.literary_text_ids:
            return self.literary_text_ids[work_local_id]

        # Check DB
        existing = db.scalar(
            select(LiteraryText.id).where(LiteraryText.local_id == work_local_id)
        )
        if existing:
            self.literary_text_ids[work_local_id] = existing
            return existing

        stmt = (
            insert(LiteraryText)
            .values(local_id=work_local_id)
            .on_conflict_do_nothing(index_elements=["local_id"])
            .returning(LiteraryText.id)
        )
        result = db.execute(stmt)
        row = result.fetchone()
        if row:
            parent_id: int = row[0]
        else:
            parent_id = db.scalar(
                select(LiteraryText.id).where(LiteraryText.local_id == work_local_id)
            )
        self.literary_text_ids[work_local_id] = parent_id
        self.stats.inserted_works += 1
        return parent_id

    def _insert_version(self, db: Session, text_data: Dict) -> None:
        """Insert a LiteraryTextLangVersion and its segments into the session."""
        local_id = text_data["local_id"]
        language_code = text_data.get("language", "grc")
        lang_enum = LANGUAGE_MAP.get(language_code, Language.GRC)

        work_local_id = ".".join(local_id.split(".")[:2])
        parent_id = self._ensure_parent_record(db, work_local_id)

        version = LiteraryTextLangVersion(
            local_id=local_id,
            literary_text_id=parent_id,
            language=lang_enum,
            author=text_data.get("author", "Unknown"),
            title=text_data.get("title", "Unknown"),
            translator=text_data.get("translator"),
        )
        db.add(version)
        db.flush()

        for seg_data in text_data["segments"]:
            db.add(
                TextSegment(
                    lang_version_id=version.id,
                    book=seg_data["book"],
                    line=seg_data["line"],
                    reference=seg_data["reference"],
                    content=seg_data["content"],
                    sequence=seg_data["sequence"],
                )
            )
            self.stats.total_segments += 1

        self.stats.inserted_versions += 1

    def run(self, db: Session) -> LLMPopulateStats:
        """Main entry point: parse XML files via LLM and populate the database."""
        start_time = time.time()

        if not openrouter_config.API_KEY or openrouter_config.API_KEY == "<your-key-here>":
            raise ValueError(
                "OPENROUTER_API_KEY is not set. "
                "Add it to backend/.env and run again."
            )

        self._init_llm_parser()
        self._prefetch_existing_version_ids(db)

        if self.config.from_failures_file:
            failures_path = self.config.from_failures_file
            if not failures_path.exists():
                raise FileNotFoundError(f"Failures file not found: {failures_path}")
            payload = json.loads(failures_path.read_text(encoding="utf-8"))
            xml_files = [Path(p) for p in payload.get("failed_files", [])]
            logger.info("Loaded %d failed files from %s", len(xml_files), failures_path)
        else:
            data_dir = self.config.data_dir or Path(settings.assets.PERSEUS_DATA_DIR)
            if not data_dir.exists():
                raise FileNotFoundError(f"Data directory not found: {data_dir}")
            xml_files = [
                p
                for p in data_dir.rglob("*.xml")
                if p.name not in ("__cts__.xml", "build.xml", "collection.xconf")
            ]

        if self.config.limit:
            xml_files = xml_files[: self.config.limit]
            logger.info("Limited to first %d files", self.config.limit)

        logger.info("Processing %d XML files via LLM (%s)…", len(xml_files), self.llm_parser.model)

        batch_count = 0
        for xml_file in xml_files:
            try:
                if self.config.dry_run:
                    logger.info("DRY RUN: would process %s", xml_file.name)
                    self.stats.files_processed += 1
                    continue

                # Pre-LLM skip: if filename-derived local_id is already in DB,
                # don't waste an LLM call. The post-LLM check below is kept as
                # a safety net for files where the derived id differs.
                filename_id = XMLChunker(
                    xml_text=""
                ).filename_local_id(xml_file)
                if filename_id in self.existing_version_ids:
                    self.stats.skipped += 1
                    logger.debug("Pre-skip %s (already exists)", filename_id)
                    continue

                text_data = self.llm_parser.parse_file(xml_file)
                if not text_data:
                    self.stats.errors += 1
                    continue

                local_id = text_data["local_id"]
                language = text_data.get("language", "grc")

                if not self._should_process(local_id, language):
                    self.stats.skipped += 1
                    logger.debug("Skipped %s (already exists or filtered)", local_id)
                    continue

                try:
                    self._insert_version(db, text_data)
                except IntegrityError as ie:
                    db.rollback()
                    logger.warning(
                        "IntegrityError inserting %s: %s — skipping",
                        local_id,
                        ie,
                    )
                    self.stats.errors += 1
                    continue

                self.existing_version_ids.add(local_id)
                self.stats.files_processed += 1
                self.stats.llm_calls = self.llm_parser._call_count
                batch_count += 1

                if batch_count >= self.config.commit_batch:
                    db.commit()
                    logger.info(
                        "Committed batch: %d versions, %d segments (LLM calls so far: %d)",
                        self.stats.inserted_versions,
                        self.stats.total_segments,
                        self.stats.llm_calls,
                    )
                    batch_count = 0

            except Exception as exc:
                logger.error("Error processing %s: %s", xml_file.name, exc)
                self.stats.errors += 1
                if self.config.fail_fast:
                    db.rollback()
                    raise

        if batch_count > 0:
            db.commit()

        self.stats.llm_calls = self.llm_parser._call_count if self.llm_parser else 0
        self.stats.processing_time = time.time() - start_time
        return self.stats


# ---------------------------------------------------------------------------
# Top-level runner
# ---------------------------------------------------------------------------


def run_llm_population(config: LLMPopulateConfig) -> LLMPopulateStats:
    """Run the LLM-based population with the given config."""
    logger.info("Starting LLM-based population: %s", config)
    db = SessionLocal()
    try:
        populator = LLMDatabasePopulator(config)
        stats = populator.run(db)

        logger.info("Population complete!")
        logger.info("  Works inserted:    %d", stats.inserted_works)
        logger.info("  Versions inserted: %d", stats.inserted_versions)
        logger.info("  Segments inserted: %d", stats.total_segments)
        logger.info("  Skipped:           %d", stats.skipped)
        logger.info("  Errors:            %d", stats.errors)
        logger.info("  LLM API calls:     %d", stats.llm_calls)
        logger.info("  Processing time:   %.2fs", stats.processing_time)
        return stats
    finally:
        db.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    )

    ap = argparse.ArgumentParser(
        description="Populate database with Perseus texts using an LLM (OpenRouter)"
    )
    ap.add_argument("--limit", type=int, help="Limit number of XML files to process")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover files and log what would be done, without calling the LLM",
    )
    ap.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "OpenRouter model ID to use "
            "(default: value of OPENROUTER_MODEL env var). "
            "Free examples: meta-llama/llama-3.1-8b-instruct:free, "
            "google/gemma-2-9b-it:free, mistralai/mistral-7b-instruct:free"
        ),
    )
    ap.add_argument(
        "--languages",
        nargs="*",
        default=[],
        help="Filter by language codes (grc, lat, en)",
    )
    ap.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of versions to accumulate before committing to DB",
    )
    ap.add_argument(
        "--fail-fast",
        action="store_true",
        default=False,
        help="Abort on the first error instead of continuing",
    )
    ap.add_argument(
        "--data-dir",
        type=Path,
        help="Override the Perseus data directory (default: PERSEUS_DATA_DIR setting)",
    )
    ap.add_argument(
        "--from-failures-file",
        type=Path,
        default=None,
        help=(
            "Process only the files listed in the given JSON file "
            "(format: {\"failed_files\": [<path>, ...]}, as written by "
            "populate_database.py). Skips the data-dir rglob."
        ),
    )

    args = ap.parse_args()

    config = LLMPopulateConfig(
        limit=args.limit,
        dry_run=args.dry_run,
        languages=args.languages,
        commit_batch=args.batch_size,
        fail_fast=args.fail_fast,
        data_dir=args.data_dir,
        model=args.model,
        from_failures_file=args.from_failures_file,
    )

    stats = run_llm_population(config)
    sys.exit(0 if stats.errors == 0 else 1)
