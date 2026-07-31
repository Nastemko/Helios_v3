"""Audit the Perseus TEI corpus against the schema the populators assume.

Read-only and database-free: this parses every text file and every __cts__.xml
with the same parsers used by populate_database.py, then reports the files that
deviate from the expected shape. Run it before a load to see which texts would
be dropped or degraded, and after a parser change as a regression check.

Checks performed:
- every text file on disk resolves to a CTS-registered version (and vice versa)
- author and title are resolved rather than falling back to "Unknown"
- the CTS language maps to a Language enum member
- the file yields at least one segment
- segment references are non-empty and unique within a version
- every work directory has a __cts__.xml
"""

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from config import settings
from parsers.cts_metadata_parser import CTSMetadataParser
from parsers.perseus_xml_parser import PerseusXMLParser
from scripts.populate_database import LANGUAGE_MAP, UNSUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)


@dataclass
class ValidateConfig:
    """Configuration for a corpus validation run."""

    data_dir: Optional[Path] = None
    report_output: Optional[Path] = None
    examples: int = 10


@dataclass
class ValidationReport:
    """Findings from a corpus validation run."""

    total_files: int = 0
    total_cts_works: int = 0
    total_cts_versions: int = 0
    total_segments: int = 0
    parse_failures: List[str] = field(default_factory=list)
    zero_segments: List[str] = field(default_factory=list)
    missing_cts_entry: List[str] = field(default_factory=list)
    cts_without_file: List[str] = field(default_factory=list)
    unknown_author: List[str] = field(default_factory=list)
    unknown_title: List[str] = field(default_factory=list)
    unsupported_language: List[str] = field(default_factory=list)
    duplicate_references: List[str] = field(default_factory=list)
    empty_references: List[str] = field(default_factory=list)
    work_dirs_without_cts: List[str] = field(default_factory=list)
    language_counts: Dict[str, int] = field(default_factory=dict)

    def is_clean(self) -> bool:
        """Whether every blocking check passed."""
        return not (
            self.parse_failures
            or self.zero_segments
            or self.missing_cts_entry
            or self.cts_without_file
            or self.unknown_author
            or self.unknown_title
            or self.empty_references
        )


class CorpusValidator:
    """Cross-check the on-disk corpus against the populator's expectations."""

    def __init__(self, config: ValidateConfig):
        self.config = config
        self.report = ValidationReport()

    def validate(self) -> ValidationReport:
        """
        Run every check over the corpus.

        Returns:
            The populated ValidationReport
        """
        data_dir = self.config.data_dir or Path(settings.assets.PERSEUS_DATA_DIR)
        if not data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {data_dir}")

        logger.info("Validating corpus at %s", data_dir)

        cts_parser = CTSMetadataParser(data_dir)
        cts_data = cts_parser.parse_all()
        self.report.total_cts_works = len(cts_data)

        cts_versions = {
            version.local_id: version
            for work in cts_data.values()
            for version in work.versions
        }
        self.report.total_cts_versions = len(cts_versions)

        self._check_work_dirs(data_dir)

        parser = PerseusXMLParser(data_dir)
        xml_files = parser.find_all_text_files()
        self.report.total_files = len(xml_files)

        languages: Counter = Counter()
        seen_local_ids = set()

        for xml_file in xml_files:
            text_data = parser.parse_file(xml_file)
            if text_data is None:
                self.report.parse_failures.append(str(xml_file))
                continue

            local_id = text_data["local_id"]
            seen_local_ids.add(local_id)

            segments = text_data["segments"]
            self.report.total_segments += len(segments)
            if not segments:
                self.report.zero_segments.append(str(xml_file))

            version_info = cts_parser.get_version_info(local_id)
            if version_info is None:
                self.report.missing_cts_entry.append(str(xml_file))
                language = text_data.get("language", "grc")
                author = text_data.get("author", "Unknown")
                title = text_data.get("title", "Unknown")
            else:
                language = version_info.language
                author = version_info.author
                title = version_info.title

            languages[language] += 1

            if author == "Unknown":
                self.report.unknown_author.append(local_id)
            if title == "Unknown":
                self.report.unknown_title.append(local_id)

            if language in UNSUPPORTED_LANGUAGES or language not in LANGUAGE_MAP:
                self.report.unsupported_language.append(f"{local_id} ({language})")

            self._check_references(local_id, segments)

        for local_id in sorted(set(cts_versions) - seen_local_ids):
            self.report.cts_without_file.append(local_id)

        self.report.language_counts = dict(languages.most_common())
        return self.report

    def _check_work_dirs(self, data_dir: Path) -> None:
        """
        Flag work directories that have no __cts__.xml.

        Args:
            data_dir: Corpus root
        """
        for work_dir in sorted(data_dir.glob("*/*")):
            if not work_dir.is_dir():
                continue
            if not (work_dir / "__cts__.xml").exists():
                self.report.work_dirs_without_cts.append(str(work_dir))

    def _check_references(self, local_id: str, segments: List[Dict]) -> None:
        """
        Flag empty or non-unique segment references within one version.

        Args:
            local_id: Version identifier, for reporting
            segments: Parsed segments for that version
        """
        references = [segment["reference"] for segment in segments]
        if any(not reference for reference in references):
            self.report.empty_references.append(local_id)
        if len(set(references)) != len(references):
            duplicates = len(references) - len(set(references))
            self.report.duplicate_references.append(f"{local_id} ({duplicates} dupes)")


def _print_section(title: str, entries: List[str], examples: int) -> None:
    """
    Print one finding group with a capped list of examples.

    Args:
        title: Human-readable check name
        entries: Offending items
        examples: Maximum examples to show
    """
    status = "OK  " if not entries else "FAIL"
    print(f"  [{status}] {title:38s} {len(entries)}")
    for entry in entries[:examples]:
        print(f"           - {entry}")
    if len(entries) > examples:
        print(f"           ... and {len(entries) - examples} more")


def print_report(report: ValidationReport, examples: int) -> None:
    """
    Write a human-readable summary to stdout.

    Args:
        report: Findings to render
        examples: Maximum examples per check
    """
    print("\n=== Perseus corpus validation ===")
    print(f"  text files:    {report.total_files}")
    print(f"  CTS works:     {report.total_cts_works}")
    print(f"  CTS versions:  {report.total_cts_versions}")
    print(f"  segments:      {report.total_segments}")

    print("\n  languages:")
    for language, count in report.language_counts.items():
        mapped = LANGUAGE_MAP.get(language)
        label = mapped.value if mapped else "UNSUPPORTED"
        print(f"    {language:6s} -> {label:12s} {count}")

    print("\n  checks:")
    _print_section("files that failed to parse", report.parse_failures, examples)
    _print_section("files with zero segments", report.zero_segments, examples)
    _print_section("files with no CTS entry", report.missing_cts_entry, examples)
    _print_section("CTS versions with no file", report.cts_without_file, examples)
    _print_section("versions with Unknown author", report.unknown_author, examples)
    _print_section("versions with Unknown title", report.unknown_title, examples)
    _print_section("versions with empty references", report.empty_references, examples)

    print("\n  informational:")
    # Duplicate references survive only where the source itself repeats an @n
    # (e.g. two <l n="327"> across a speech boundary), so they do not block.
    _print_section(
        "versions with duplicate references", report.duplicate_references, examples
    )
    _print_section(
        "skipped: unsupported language", report.unsupported_language, examples
    )
    _print_section(
        "work dirs without __cts__.xml", report.work_dirs_without_cts, examples
    )

    verdict = "CLEAN" if report.is_clean() else "ISSUES FOUND"
    print(f"\n  verdict: {verdict}\n")


def run_validation(config: ValidateConfig) -> ValidationReport:
    """
    Validate the corpus and optionally write a JSON report.

    Args:
        config: Validation configuration

    Returns:
        The populated ValidationReport
    """
    validator = CorpusValidator(config)
    report = validator.validate()

    print_report(report, config.examples)

    if config.report_output:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "data_dir": str(config.data_dir or settings.assets.PERSEUS_DATA_DIR),
            "totals": {
                "text_files": report.total_files,
                "cts_works": report.total_cts_works,
                "cts_versions": report.total_cts_versions,
                "segments": report.total_segments,
            },
            "language_counts": report.language_counts,
            "findings": {
                "parse_failures": report.parse_failures,
                "zero_segments": report.zero_segments,
                "missing_cts_entry": report.missing_cts_entry,
                "cts_without_file": report.cts_without_file,
                "unknown_author": report.unknown_author,
                "unknown_title": report.unknown_title,
                "unsupported_language": report.unsupported_language,
                "duplicate_references": report.duplicate_references,
                "empty_references": report.empty_references,
                "work_dirs_without_cts": report.work_dirs_without_cts,
            },
            "clean": report.is_clean(),
        }
        config.report_output.parent.mkdir(parents=True, exist_ok=True)
        config.report_output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Wrote JSON report to %s", config.report_output)

    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(message)s")

    ap = argparse.ArgumentParser(
        description="Validate the Perseus corpus against the populator's schema"
    )
    ap.add_argument("--data-dir", type=Path, help="Override data directory")
    ap.add_argument("--report", type=Path, help="Write a JSON report to this path")
    ap.add_argument(
        "--examples",
        type=int,
        default=10,
        help="Maximum example paths to print per check",
    )

    args = ap.parse_args()

    validation_config = ValidateConfig(
        data_dir=args.data_dir,
        report_output=args.report,
        examples=args.examples,
    )

    validation_report = run_validation(validation_config)
    sys.exit(0 if validation_report.is_clean() else 1)
