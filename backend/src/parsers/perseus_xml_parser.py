"""Parser for Perseus TEI XML files"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import lxml.etree as ET

logger = logging.getLogger(__name__)


class PerseusXMLParser:
    """Parse Perseus TEI XML files to extract text and metadata"""

    # XML Namespaces
    TEI_NS = "{http://www.tei-c.org/ns/1.0}"
    CTS_NS = "{http://chs.harvard.edu/xmlns/cts}"
    TI_NS = "{http://chs.harvard.edu/xmlns/cts}"  # CTS Text Inventory namespace

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

            # Extract URN from div element
            urn = self._extract_urn(root)
            if not urn:
                logger.warning(f"No URN found in {xml_path}")
                return None

            # Determine language from URN or XML
            language = self._extract_language(root, urn)

            # Extract metadata from teiHeader
            metadata = self._extract_metadata(root)

            # Try to get English title from __cts__.xml in the same directory
            english_title = self._extract_english_title_from_cts(xml_path)
            
            # Use English title if available, otherwise fall back to native title from header
            title = english_title or metadata.get("title", "Unknown")

            # Extract text segments
            segments = self._extract_text_segments(root)

            if not segments:
                logger.warning(f"No text segments found in {xml_path}")
                return None

            return {
                "urn": urn,
                "author": metadata.get("author", "Unknown"),
                "title": title,
                "language": language,
                "is_fragment": False,  # TODO: determine from metadata
                "text_metadata": metadata,
                "segments": segments,
            }

        except Exception as e:
            logger.error(f"Error parsing {xml_path}: {e}")
            return None

    def _extract_english_title_from_cts(self, xml_path: Path) -> Optional[str]:
        """
        Extract English title from __cts__.xml file in the same directory

        Args:
            xml_path: Path to the main XML file

        Returns:
            English title string or None if not found
        """
        try:
            cts_path = xml_path.parent / "__cts__.xml"
            if not cts_path.exists():
                return None

            tree = ET.parse(str(cts_path))
            root = tree.getroot()

            # Look for ti:title with xml:lang="eng"
            # The namespace is typically "http://chs.harvard.edu/xmlns/cts"
            for ns_prefix in ["ti", ""]:
                ns = self.TI_NS if ns_prefix else ""
                
                # Try to find title element with English language
                for title_elem in root.iter():
                    if title_elem.tag.endswith("title"):
                        lang = title_elem.get("{http://www.w3.org/XML/1998/namespace}lang")
                        if lang == "eng" and title_elem.text:
                            return title_elem.text.strip()

            return None

        except Exception as e:
            logger.debug(f"Could not extract English title from CTS file for {xml_path}: {e}")
            return None

    def _extract_urn(self, root: ET.Element) -> Optional[str]:
        """Extract URN from document"""
        # Try to get URN from div[@type='edition']
        div = root.find(f".//{self.TEI_NS}div[@type='edition']")
        if div is not None:
            urn = div.get("n")
            if urn:
                return urn

        return None

    def _extract_language(self, root: ET.Element, urn: str) -> str:
        """
        Extract language code

        Args:
            root: XML root element
            urn: Text URN

        Returns:
            Language code ('grc' for Greek, 'lat' for Latin)
        """
        # Try to get from div xml:lang
        div = root.find(f".//{self.TEI_NS}div[@type='edition']")
        if div is not None:
            lang = div.get("{http://www.w3.org/XML/1998/namespace}lang")
            if lang:
                return lang

        # Infer from URN
        if "greekLit" in urn:
            return "grc"
        elif "latinLit" in urn:
            return "lat"

        return "grc"  # Default to Greek

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
        segments = []
        sequence = 0

        # Find the body/text content
        body = root.find(f".//{self.TEI_NS}body")
        if body is None:
            return segments

        # Find all textpart divisions (books, chapters, etc.)
        textparts = body.findall(f".//{self.TEI_NS}div[@type='textpart']")

        if textparts:
            # Text is divided into books/chapters/sections
            for textpart in textparts:
                subtype = textpart.get("subtype", "")
                section_num = textpart.get("n", "")

                # Find all lines within this textpart
                lines = textpart.findall(f".//{self.TEI_NS}l")
                for line in lines:
                    line_num = line.get("n", "")
                    content = self._extract_text_content(line)

                    if content:
                        segments.append(
                            {
                                "book": section_num,
                                "line": line_num,
                                "reference": f"{section_num}.{line_num}"
                                if section_num
                                else line_num,
                                "content": content,
                                "sequence": sequence,
                            }
                        )
                        sequence += 1

                # If no lines found, check for paragraphs within this textpart
                if not lines:
                    paras = textpart.findall(f".//{self.TEI_NS}p")
                    for para in paras:
                        content = self._extract_text_content(para)
                        if content:
                            segments.append(
                                {
                                    "book": section_num,
                                    "line": "",
                                    "reference": section_num,
                                    "content": content,
                                    "sequence": sequence,
                                }
                            )
                            sequence += 1
        else:
            # Text without explicit textparts - try to find all lines
            lines = body.findall(f".//{self.TEI_NS}l")
            for line in lines:
                line_num = line.get("n", "")
                content = self._extract_text_content(line)

                if content:
                    segments.append(
                        {
                            "book": "",
                            "line": line_num,
                            "reference": line_num,
                            "content": content,
                            "sequence": sequence,
                        }
                    )
                    sequence += 1

            # Also try paragraphs if no lines found
            if not segments:
                paras = body.findall(f".//{self.TEI_NS}p")
                for idx, para in enumerate(paras):
                    content = self._extract_text_content(para)
                    if content:
                        segments.append(
                            {
                                "book": "",
                                "line": str(idx + 1),
                                "reference": str(idx + 1),
                                "content": content,
                                "sequence": sequence,
                            }
                        )
                        sequence += 1

        return segments

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

        return xml_files

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
