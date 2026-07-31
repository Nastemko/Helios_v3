"""Parser for CTS (__cts__.xml) metadata files.

Parses the Canonical Text Services metadata format to extract:
- Author from textgroup files
- Title from work files
- Language and translator from edition/translation elements
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import lxml.etree as ET

logger = logging.getLogger(__name__)

CTS_NS = "{http://chs.harvard.edu/xmlns/cts}"
XML_NS = "{http://www.w3.org/XML/1998/namespace}"


@dataclass
class VersionInfo:
    """Information about a specific version (edition or translation)."""

    local_id: str
    work_local_id: str
    language: str
    author: str
    title: str
    translator: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None


@dataclass
class WorkInfo:
    """Information about a work and all its versions."""

    work_local_id: str
    author: str
    title: str
    versions: List[VersionInfo] = field(default_factory=list)


class CTSMetadataParser:
    """Parse CTS metadata files to build a lookup table for text processing."""

    def __init__(self, data_dir: Path):
        """
        Initialize parser.

        Args:
            data_dir: Path to canonical-greekLit/data directory
        """
        self.data_dir = Path(data_dir)
        self._textgroup_cache: Dict[str, str] = {}
        self._work_cache: Dict[str, WorkInfo] = {}

    def parse_all(self) -> Dict[str, WorkInfo]:
        """
        Parse all CTS metadata files in the data directory.

        Returns:
            Dictionary mapping work_local_id to WorkInfo
        """
        self._parse_all_textgroups()
        self._parse_all_works()
        return self._work_cache

    def _parse_all_textgroups(self) -> None:
        """Parse all textgroup __cts__.xml files to extract author names."""
        for cts_file in self.data_dir.glob("*/__cts__.xml"):
            try:
                self._parse_textgroup(cts_file)
            except Exception as e:
                logger.warning(
                    "Error parsing textgroup %s: %s: %s",
                    cts_file,
                    type(e).__name__,
                    e,
                )

    def _parse_textgroup(self, cts_file: Path) -> str:
        """
        Parse a textgroup __cts__.xml file.

        Args:
            cts_file: Path to textgroup __cts__.xml

        Returns:
            Textgroup ID (e.g., "tlg0012")
        """
        tree = ET.parse(str(cts_file))
        root = tree.getroot()

        # The textgroup element is the root element. Prefer @urn: 42 of the 100
        # textgroup files in canonical-greekLit omit @projid but all carry @urn.
        # Keying off projid alone collapsed those onto an empty key, which made
        # every work in them fall back to author="Unknown".
        raw_id = root.get("urn") or root.get("projid") or ""
        textgroup_id = raw_id.rsplit(":", 1)[-1] if raw_id else ""
        if not textgroup_id:
            logger.warning(
                "Textgroup %s has neither @urn nor @projid; author unavailable",
                cts_file,
            )
            return ""

        groupname = root.find(f"{CTS_NS}groupname")
        author = (
            groupname.text.strip()
            if groupname is not None and groupname.text
            else "Unknown"
        )

        self._textgroup_cache[textgroup_id] = author
        return textgroup_id

    def _parse_all_works(self) -> None:
        """Parse all work __cts__.xml files to extract work and version info."""
        for cts_file in self.data_dir.glob("*/*/__cts__.xml"):
            try:
                self._parse_work(cts_file)
            except Exception as e:
                logger.warning(
                    "Error parsing work %s: %s: %s", cts_file, type(e).__name__, e
                )

    def _parse_work(self, cts_file: Path) -> Optional[WorkInfo]:
        """
        Parse a work __cts__.xml file.

        Args:
            cts_file: Path to work __cts__.xml

        Returns:
            WorkInfo object or None if parsing fails
        """
        tree = ET.parse(str(cts_file))
        root = tree.getroot()

        # The work element is the root element
        work = root
        if not work.tag.endswith("work"):
            raise ValueError(f"No work element in {cts_file}")

        urn = work.get("urn", "")
        work_local_id = self._extract_local_id_from_urn(urn)
        if not work_local_id:
            raise ValueError(f"Could not extract work_local_id from urn: {urn}")

        textgroup_id = work_local_id.split(".")[0]

        # Try to get Greek title first, then any title, then English
        title = "Unknown"
        title_elem_grc = work.find(f"{CTS_NS}title[@{XML_NS}lang='grc']")
        if title_elem_grc is not None and title_elem_grc.text:
            title = title_elem_grc.text.strip()
        else:
            # Find any title that's not English
            for title_elem in work.findall(f"{CTS_NS}title"):
                lang = title_elem.get(f"{XML_NS}lang", "")
                if lang != "eng" and title_elem.text:
                    title = title_elem.text.strip()
                    break
            else:
                # Fall back to English title
                title_elem_eng = work.find(f"{CTS_NS}title[@{XML_NS}lang='eng']")
                if title_elem_eng is not None and title_elem_eng.text:
                    title = title_elem_eng.text.strip()
                else:
                    title_elem = work.find(f"{CTS_NS}title")
                    if title_elem is not None and title_elem.text:
                        title = title_elem.text.strip()

        author = self._textgroup_cache.get(textgroup_id, "Unknown")

        work_info = WorkInfo(
            work_local_id=work_local_id,
            author=author,
            title=title,
        )

        for edition in work.findall(f"{CTS_NS}edition"):
            version_info = self._parse_version(edition, work_local_id, author, title)
            if version_info:
                work_info.versions.append(version_info)

        for translation in work.findall(f"{CTS_NS}translation"):
            version_info = self._parse_version(
                translation, work_local_id, author, title
            )
            if version_info:
                work_info.versions.append(version_info)

        self._work_cache[work_local_id] = work_info
        return work_info

    def _parse_version(
        self,
        element: ET.Element,
        work_local_id: str,
        work_author: str,
        work_title: str,
    ) -> Optional[VersionInfo]:
        """
        Parse a version (edition or translation) element.

        Args:
            element: The edition or translation XML element
            work_local_id: The work's local ID
            work_author: The author's name (for storing in version)
            work_title: The work's title (for fallback if no localized title)

        Returns:
            VersionInfo or None
        """
        urn = element.get("urn", "")
        local_id = self._extract_local_id_from_urn(urn)
        if not local_id:
            return None

        language = element.get("{http://www.w3.org/XML/1998/namespace}lang", "grc")

        is_translation = element.tag == f"{CTS_NS}translation"

        title = work_title
        title_elem = element.find(f"{CTS_NS}label[@{XML_NS}lang='{language}']")
        if title_elem is None:
            title_elem = element.find(f"{CTS_NS}label[@{XML_NS}lang='eng']")
        if title_elem is None:
            title_elem = element.find(f"{CTS_NS}label")
        if title_elem is not None and title_elem.text:
            title = title_elem.text.strip()

        label = title

        desc_elem = element.find(f"{CTS_NS}description")
        description = (
            desc_elem.text.strip() if desc_elem is not None and desc_elem.text else None
        )

        translator = None
        if is_translation:
            if description:
                translator = self._extract_translator(description)
            if not translator:
                translator = "unknown"

        return VersionInfo(
            local_id=local_id,
            work_local_id=work_local_id,
            language=language,
            author=work_author,
            title=title,
            translator=translator,
            label=label,
            description=description,
        )

    def _extract_local_id_from_urn(self, urn: str) -> Optional[str]:
        """
        Extract local_id from a CTS URN.

        Args:
            urn: CTS URN like "urn:cts:greekLit:tlg0012.tlg001.perseus-grc2"

        Returns:
            Local ID like "tlg0012.tlg001.perseus-grc2" or None
        """
        if not urn:
            return None
        parts = urn.split(":")
        if len(parts) >= 4:
            return parts[3]
        return None

    def _extract_translator(self, description: str) -> Optional[str]:
        """
        Extract translator name from description text.

        Args:
            description: Description text like "Homer. The Iliad... Murray, A. T., translator."

        Returns:
            Translator name or None
        """
        if not description:
            return None

        description = description.strip()

        # Pattern 1: Match "Last, First, translator" format (e.g., "Long, George, translator")
        # This handles the common format where the last name comes first
        pattern = r"([A-Z][a-zA-Z]*,\s*[A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)?),\s*(?:translator|translated)"
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            translator = match.group(1).strip()
            translator = re.sub(r"\s+", " ", translator)
            if len(translator) > 3 and not any(
                x in translator.lower() for x in ["london", "new york", "press", "sons"]
            ):
                return translator

        # Pattern 2: Match "First Last, translator" format (e.g., "Thomas Wentworth, translator")
        pattern = r"([A-Z][a-zA-Z]*(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-zA-Z]*)+),\s*(?:translator|translated)"
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            translator = match.group(1).strip()
            translator = re.sub(r"\s+", " ", translator)
            if len(translator) > 3 and not any(
                x in translator.lower() for x in ["london", "new york", "press", "sons"]
            ):
                return translator

        # Pattern 3: Match "translator. Name" but only capture the name part
        # Be more restrictive - translator name should not contain colons or publication info
        pattern = (
            r"translator[.,]\s+([A-Z][a-zA-Z]*(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-zA-Z]*)+)"
        )
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            translator = match.group(1).strip()
            translator = re.sub(r"\s+", " ", translator)
            if len(translator) > 3 and not any(
                x in translator.lower() for x in ["london", "new york", "press", "sons"]
            ):
                return translator

        # Pattern 4: Match "translated by Name"
        pattern = (
            r"translated by\s+([A-Z][a-zA-Z]*(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-zA-Z]*)+)"
        )
        match = re.search(pattern, description, re.IGNORECASE)
        if match:
            translator = match.group(1).strip()
            translator = re.sub(r"\s+", " ", translator)
            if len(translator) > 3 and not any(
                x in translator.lower() for x in ["london", "new york", "press", "sons"]
            ):
                return translator

        return None

    def get_version_info(self, local_id: str) -> Optional[VersionInfo]:
        """
        Get version info for a specific local_id.

        Args:
            local_id: Full local_id like "tlg0012.tlg001.perseus-eng3" or "greekLit:tlg0012.tlg001.perseus-eng3"

        Returns:
            VersionInfo or None if not found
        """
        # Normalize local_id by stripping namespace prefix if present
        if ":" in local_id:
            local_id = local_id.split(":")[-1]

        work_local_id = ".".join(local_id.split(".")[:2])

        work_info = self._work_cache.get(work_local_id)
        if not work_info:
            return None

        for version in work_info.versions:
            if version.local_id == local_id:
                return version

        return None

    def get_work_info(self, work_local_id: str) -> Optional[WorkInfo]:
        """
        Get work info for a specific work_local_id.

        Args:
            work_local_id: Work ID like "tlg0012.tlg001"

        Returns:
            WorkInfo or None if not found
        """
        return self._work_cache.get(work_local_id)
