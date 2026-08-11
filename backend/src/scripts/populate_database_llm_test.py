"""Tests for LLM populator transaction handling.

These cover the resumability contract: a file that fails to insert must not
take previously-inserted files in the same uncommitted batch down with it,
and must never be recorded as "already present" unless it actually committed.
"""

from pathlib import Path
from typing import Dict, List, Optional
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database import Base
from models.text import LiteraryText, LiteraryTextLangVersion, TextSegment
from scripts.populate_database_llm import (
    LLMPopulateConfig,
    LLMDatabasePopulator,
)


@pytest.fixture
def db():
    """In-memory SQLite session with just the literary-text tables.

    Only these three are created: the `inscriptions` table uses a JSONB column
    that the SQLite dialect cannot render, and it is irrelevant here.
    """
    engine = create_engine("sqlite://")
    Base.metadata.create_all(
        engine,
        tables=[
            LiteraryText.__table__,
            LiteraryTextLangVersion.__table__,
            TextSegment.__table__,
        ],
    )
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _text_data(local_id: str) -> Dict:
    """Minimal well-formed parse result for one work."""
    return {
        "local_id": local_id,
        "language": "grc",
        "author": "Test Author",
        "title": f"Work {local_id}",
        "segments": [
            {
                "book": "1",
                "line": "1",
                "reference": "1.1",
                "content": "μῆνιν ἄειδε θεά",
                "sequence": 1,
            }
        ],
    }


class _StubParser:
    """Stands in for LLMXMLParser, returning canned parses keyed by filename."""

    def __init__(self, by_name: Dict[str, Optional[Dict]]) -> None:
        self._by_name = by_name
        self._call_count = 0
        self.model = "stub-model"

    def parse_file(self, xml_file: Path) -> Optional[Dict]:
        self._call_count += 1
        return self._by_name.get(xml_file.name)

    def filename_local_id(self, xml_file: Path) -> str:
        return xml_file.stem


def _run_populator(
    db,
    files: List[Path],
    parses: Dict[str, Optional[Dict]],
    failing_local_id: str,
    commit_batch: int = 50,
) -> LLMDatabasePopulator:
    """Drive the real run loop, forcing one insert to raise IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    config = LLMPopulateConfig(commit_batch=commit_batch)
    populator = LLMDatabasePopulator(config)
    populator.llm_parser = _StubParser(parses)

    real_insert = populator._insert_version

    def flaky_insert(session, text_data: Dict) -> None:
        if text_data["local_id"] == failing_local_id:
            raise IntegrityError("stmt", {}, Exception("duplicate key"))
        return real_insert(session, text_data)

    with (
        patch.object(populator, "_insert_version", side_effect=flaky_insert),
        patch.object(populator, "_init_llm_parser"),
        patch.object(populator, "_prefetch_existing_version_ids"),
        patch("scripts.populate_database_llm.openrouter_config") as cfg,
        patch.object(Path, "rglob", return_value=files),
        patch.object(Path, "exists", return_value=True),
    ):
        cfg.API_KEY = "test-key"
        populator.run(db)

    return populator


def test_integrity_error_preserves_earlier_files_in_batch(db):
    """A mid-batch IntegrityError must not discard already-inserted versions.

    With commit_batch=50, files 1 and 2 sit uncommitted when file 3 fails.
    A bare session.rollback() throws all three away.
    """
    files = [Path(f"tlg0012.tlg00{i}.perseus-grc1.xml") for i in (1, 2, 3, 4)]
    parses = {f.name: _text_data(f.stem) for f in files}

    populator = _run_populator(
        db, files, parses, failing_local_id="tlg0012.tlg003.perseus-grc1"
    )

    stored = {
        row.local_id for row in db.execute(select(LiteraryTextLangVersion)).scalars()
    }

    # The three healthy files must all survive the one bad one.
    assert "tlg0012.tlg001.perseus-grc1" in stored
    assert "tlg0012.tlg002.perseus-grc1" in stored
    assert "tlg0012.tlg004.perseus-grc1" in stored
    assert "tlg0012.tlg003.perseus-grc1" not in stored


def test_failed_file_not_marked_as_existing(db):
    """The failing file must not be recorded as present, or a resume skips it forever."""
    files = [Path(f"tlg0012.tlg00{i}.perseus-grc1.xml") for i in (1, 2)]
    parses = {f.name: _text_data(f.stem) for f in files}

    populator = _run_populator(
        db, files, parses, failing_local_id="tlg0012.tlg002.perseus-grc1"
    )

    assert "tlg0012.tlg002.perseus-grc1" not in populator.existing_version_ids


def test_stats_match_committed_rows(db):
    """Reported inserted_versions must equal what is actually in the database."""
    files = [Path(f"tlg0012.tlg00{i}.perseus-grc1.xml") for i in (1, 2, 3)]
    parses = {f.name: _text_data(f.stem) for f in files}

    populator = _run_populator(
        db, files, parses, failing_local_id="tlg0012.tlg002.perseus-grc1"
    )

    actual = len(db.execute(select(LiteraryTextLangVersion)).scalars().all())
    assert populator.stats.inserted_versions == actual
