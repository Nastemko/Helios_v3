"""Parser for Perseus TEI XML files"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import lxml.etree as ET

logger = logging.getLogger(__name__)

XML_NS = "{http://www.w3.org/XML/1998/namespace}"

# Elements that carry citable text inside a leaf textpart, in priority order.
CONTENT_CARRIERS = ("l", "p", "ab")


class PerseusXMLParser:
    """Parse Perseus TEI XML files to extract text and metadata"""

    # XML Namespaces
    TEI_NS = "{http://www.tei-c.org/ns/1.0}"
    CTS_NS = "{http://chs.harvard.edu/xmlns/cts}"

    def __init__(self, data_dir: Path):
        """
        Initialize parser

        Args:
            data_dir: Path to canonical-greekLit/data directory
        """
        self.data_dir = Path(data_dir)

    def parse_file(self, xml_path: Path) -> Optional[Dict]:
        """
        Parse a single Perseus TEI XML file

        Args:
            xml_path: Path to XML file

        Returns:
            Dictionary with text data or None if parsing fails
        """
        try:
            tree = ET.parse(str(xml_path))
            root = tree.getroot()

            # Extract local_id from div element or file path
            local_id = self._extract_local_id(root, xml_path)
            if not local_id:
                logger.warning(f"No local_id found in {xml_path}")
                return None

            # Determine language from XML
            language = self._extract_language(root)

            # Extract metadata from teiHeader
            metadata = self._extract_metadata(root)

            # Extract text segments
            segments = self._extract_text_segments(root)

            if not segments:
                logger.warning(f"No text segments found in {xml_path}")
                return None

            return {
                "local_id": local_id,
                "author": metadata.get("author", "Unknown"),
                "title": metadata.get("title", "Unknown"),
                "language": language,
                "is_fragment": False,  # TODO: determine from metadata
                "text_metadata": metadata,
                "segments": segments,
            }

        except Exception as e:
            logger.error(f"Error parsing {xml_path}: {e}")
            return None

    def _extract_local_id(self, root: ET.Element, xml_path: Path) -> Optional[str]:
        """Extract local_id from div element or file path"""
        # Try to get from div[@type='edition'] @n attribute first
        div = root.find(f".//{self.TEI_NS}div[@type='edition']")
        if div is not None:
            urn = div.get("n")
            if urn:
                # Extract everything after 3rd colon: urn:cts:greekLit:tlg0013.tlg001.perseus-grc2
                parts = urn.split(":", 3)
                if len(parts) >= 4:
                    return parts[3]

        # Also check div[@type='translation']
        div = root.find(f".//{self.TEI_NS}div[@type='translation']")
        if div is not None:
            urn = div.get("n")
            if urn:
                # Extract everything after 3rd colon: urn:cts:greekLit:tlg0013.tlg001.perseus-grc2
                parts = urn.split(":", 3)
                if len(parts) >= 4:
                    return parts[3]

        # Fallback to file path parsing
        # tl tlg0013/tlg001/tlg0013.tlg001.perseus-grc2.xml -> tlg0013.tlg001.perseus-grc2
        stem = xml_path.stem
        if ".perseus-" in stem:
            return stem
        return stem

    def _extract_language(self, root: ET.Element) -> str:
        """
        Extract language code from XML

        Args:
            root: XML root element

        Returns:
            Language code ('grc' for Greek, 'lat' for Latin)
        """
        # Try to get from div xml:lang. Translations must be checked too --
        # looking only at div[@type='edition'] silently defaulted every
        # translation file to Greek.
        for div_type in ("edition", "translation"):
            div = root.find(f".//{self.TEI_NS}div[@type='{div_type}']")
            if div is not None:
                lang = div.get(f"{XML_NS}lang")
                if lang:
                    return lang

        # Try to get from langUsage in profileDesc
        lang_usage = root.find(f".//{self.TEI_NS}langUsage")
        if lang_usage is not None:
            language = lang_usage.find(f".//{self.TEI_NS}language")
            if language is not None:
                ident = language.get("ident")
                if ident:
                    return ident

        # Default to Greek if not found
        return "grc"

    def _extract_metadata(self, root: ET.Element) -> Dict:
        """
        Extract metadata from teiHeader

        Args:
            root: XML root element

        Returns:
            Dictionary of metadata
        """
        metadata = {}

        # Find teiHeader
        header = root.find(f".//{self.TEI_NS}teiHeader")
        if header is None:
            return metadata

        # Extract title
        title_elem = header.find(f".//{self.TEI_NS}title")
        if title_elem is not None and title_elem.text:
            metadata["title"] = title_elem.text.strip()

        # Extract author
        author_elem = header.find(f".//{self.TEI_NS}author")
        if author_elem is not None and author_elem.text:
            metadata["author"] = author_elem.text.strip()

        # Extract editor(s)
        editors = []
        for editor_elem in header.findall(f".//{self.TEI_NS}editor"):
            if editor_elem.text:
                editors.append(editor_elem.text.strip())
        if editors:
            metadata["editors"] = editors

        # Extract publication info
        pub_elem = header.find(f".//{self.TEI_NS}publicationStmt")
        if pub_elem is not None:
            pub_info = {}

            publisher = pub_elem.find(f".//{self.TEI_NS}publisher")
            if publisher is not None and publisher.text:
                pub_info["publisher"] = publisher.text.strip()

            pubPlace = pub_elem.find(f".//{self.TEI_NS}pubPlace")
            if pubPlace is not None and pubPlace.text:
                pub_info["pubPlace"] = pubPlace.text.strip()

            if pub_info:
                metadata["publication"] = pub_info

        return metadata

    def _extract_text_segments(self, root: ET.Element) -> List[Dict]:
        """
        Extract text segments (lines, paragraphs, etc.)

        Args:
            root: XML root element

        Returns:
            List of segment dictionaries
        """
        segments: List[Dict] = []

        # Find the body/text content
        body = root.find(f".//{self.TEI_NS}body")
        if body is None:
            return segments

        # Recurse from each top-level div (edition/translation). Emitting only
        # at leaf textparts is what prevents the same <l> being collected once
        # per ancestor textpart.
        for top_div in body.findall(f"{self.TEI_NS}div"):
            self._collect_segments(top_div, [], segments)

        return segments

    def _is_textpart(self, element: ET.Element) -> bool:
        """
        Check whether an element is a citable textpart subdivision.

        Both <div type="textpart"> and <ab type="textpart"> occur in the corpus.

        Args:
            element: XML element

        Returns:
            True if the element subdivides the citation hierarchy
        """
        return (
            element.tag
            in (
                f"{self.TEI_NS}div",
                f"{self.TEI_NS}ab",
            )
            and element.get("type") == "textpart"
        )

    def _collect_segments(
        self, element: ET.Element, chain: List[str], segments: List[Dict]
    ) -> None:
        """
        Walk the citation hierarchy and append segments found at its leaves.

        Args:
            element: Current node in the citation tree
            chain: Ancestor @n values, forming the CTS reference (e.g. ["1", "80"])
            segments: Accumulator, mutated in place
        """
        children = [child for child in element if self._is_textpart(child)]
        if children:
            for child in children:
                self._collect_segments(child, chain + [child.get("n", "")], segments)
            return

        # Leaf: emit its content carriers, preferring lines over paragraphs.
        carriers: List[ET.Element] = []
        for tag in CONTENT_CARRIERS:
            carriers = element.findall(f".//{self.TEI_NS}{tag}")
            if carriers:
                break

        if not carriers:
            # A leaf holding text directly, with no carrier element to hang it on.
            content = self._extract_text_content(element)
            if content:
                segments.append(self._make_segment(chain, content, len(segments)))
            return

        # Carriers sharing a leaf may lack their own @n (a section holding
        # several <p>, or verse where only some lines are numbered). Fall back
        # to a positional ordinal so each segment keeps a distinct reference.
        for ordinal, carrier in enumerate(carriers, start=1):
            content = self._extract_text_content(carrier)
            if not content:
                continue
            carrier_n = carrier.get("n", "")
            if not carrier_n and len(carriers) > 1:
                carrier_n = str(ordinal)
            carrier_chain = chain + [carrier_n] if carrier_n else chain
            segments.append(self._make_segment(carrier_chain, content, len(segments)))

    def _make_segment(self, chain: List[str], content: str, sequence: int) -> Dict:
        """
        Build a segment dict from a citation chain.

        Args:
            chain: Citation components, outermost first (e.g. ["1", "80", "1"])
            content: Extracted text content
            sequence: Zero-based position within the version

        Returns:
            Segment dictionary
        """
        parts = [part for part in chain if part]
        reference = ".".join(parts) if parts else str(sequence + 1)
        return {
            "book": parts[0] if len(parts) > 1 else "",
            "line": parts[-1] if parts else "",
            "reference": reference,
            "content": content,
            "sequence": sequence,
        }

    def _extract_text_content(self, element: ET.Element) -> str:
        """
        Extract text content from an element, excluding milestone elements

        Args:
            element: XML element

        Returns:
            Cleaned text content
        """
        # Get all text, including text in child elements
        texts = []

        for text in element.itertext():
            text = text.strip()
            if text:
                texts.append(text)

        return " ".join(texts)

    def find_all_text_files(self) -> List[Path]:
        """
        Find all text XML files in the data directory

        Returns:
            List of paths to XML files (excluding __cts__.xml files)
        """
        xml_files = []

        for xml_file in self.data_dir.rglob("*.xml"):
            # Skip __cts__.xml metadata files
            if xml_file.name == "__cts__.xml":
                continue

            # Skip certain special files
            if xml_file.name in ["build.xml", "collection.xconf"]:
                continue

            xml_files.append(xml_file)

        # Sorted so that --limit selects a reproducible subset; rglob order is
        # filesystem-dependent.
        return sorted(xml_files)

    def parse_all(self, limit: Optional[int] = None) -> List[Dict]:
        """
        Parse all text files in the data directory

        Args:
            limit: Optional limit on number of files to parse (for testing)

        Returns:
            List of parsed text dictionaries
        """
        xml_files = self.find_all_text_files()
        logger.info(f"Found {len(xml_files)} XML files to parse")

        if limit:
            xml_files = xml_files[:limit]
            logger.info(f"Limited to first {limit} files")

        texts = []
        for idx, xml_file in enumerate(xml_files):
            if (idx + 1) % 100 == 0:
                logger.info(f"Parsed {idx + 1}/{len(xml_files)} files...")

            text_data = self.parse_file(xml_file)
            if text_data:
                texts.append(text_data)

        logger.info(f"Successfully parsed {len(texts)} texts")
        return texts
