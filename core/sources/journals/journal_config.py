"""Journal family configuration for the science crawler.

Each JournalFamily defines a group of journals sharing the same publisher API
and enrichment strategy (Nature/Springer, PLOS, eLife, PMC, etc.).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class JournalEntry:
    """A single journal within a family."""
    name: str = ""
    issn: str = ""
    slug: str = ""


@dataclass
class JournalFamily:
    """A group of journals sharing the same enrichment pipeline."""
    name: str = ""
    enrichment_type: str = "generic"  # nature, plos, elife, pmc, generic
    journals: List[JournalEntry] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pre-built family instances
# ---------------------------------------------------------------------------

NATURE_FAMILY = JournalFamily(
    name="Nature",
    enrichment_type="nature",
    journals=[
        JournalEntry(name="Nature", issn="0028-0836", slug="nature"),
        JournalEntry(name="Nature Methods", issn="1548-7091", slug="nmeth"),
        JournalEntry(name="Nature Biotechnology", issn="1087-0156", slug="nbt"),
        JournalEntry(name="Nature Genetics", issn="1061-4036", slug="ng"),
        JournalEntry(name="Nature Medicine", issn="1078-8956", slug="nm"),
        JournalEntry(name="Nature Communications", issn="2041-1723", slug="ncomms"),
    ],
)

SCIENCE_FAMILY = JournalFamily(
    name="Science",
    enrichment_type="pmc",
    journals=[
        JournalEntry(name="Science", issn="0036-8075", slug="science"),
        JournalEntry(name="Science Advances", issn="2375-2548", slug="sciadv"),
        JournalEntry(name="Science Translational Medicine", issn="1946-6234", slug="stm"),
    ],
)

CELL_FAMILY = JournalFamily(
    name="Cell",
    enrichment_type="pmc",
    journals=[
        JournalEntry(name="Cell", issn="0092-8674", slug="cell"),
        JournalEntry(name="Cell Reports", issn="2211-1247", slug="cell-reports"),
        JournalEntry(name="Molecular Cell", issn="1097-2765", slug="molecular-cell"),
    ],
)

PLOS_FAMILY = JournalFamily(
    name="PLOS",
    enrichment_type="plos",
    journals=[
        JournalEntry(name="PLoS ONE", issn="1932-6203", slug="plosone"),
        JournalEntry(name="PLoS Biology", issn="1544-9173", slug="plosbiology"),
        JournalEntry(name="PLoS Medicine", issn="1549-1277", slug="plosmedicine"),
        JournalEntry(name="PLoS Computational Biology", issn="1553-734X", slug="ploscompbiol"),
        JournalEntry(name="PLoS Genetics", issn="1553-7390", slug="plosgenetics"),
        JournalEntry(name="PLoS Pathogens", issn="1553-7366", slug="plospathogens"),
    ],
)

ELIFE_FAMILY = JournalFamily(
    name="eLife",
    enrichment_type="elife",
    journals=[
        JournalEntry(name="eLife", issn="2050-084X", slug="elife"),
    ],
)

PMC_FAMILY = JournalFamily(
    name="PMC",
    enrichment_type="pmc",
    journals=[
        JournalEntry(name="PMC Open Access", issn="", slug="pmc-oa"),
    ],
)

OTHER_FAMILY = JournalFamily(
    name="Other",
    enrichment_type="generic",
    journals=[],
)
