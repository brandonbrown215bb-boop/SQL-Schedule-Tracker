# data/tag_parser.py
"""Tag parser — extracts structured tags from unit descriptions.

Each description is parsed into:
  - **Unit type**: The prefix describing the unit kind (e.g. ``O)2``, ``I)3``, ``RTF``)
  - **Dimensions**: Physical dimensions extracted from the description (e.g. ``8X8X13``)
  - **Features**: Feature/component tags like ``VFD``, ``UV``, ``TCF``, ``SPPP``, etc.
  - **Flags**: Special markers enclosed in asterisks (e.g. ``*PRE-PAINT*``)

These tags are used to:
  1. Build a repository of what each detailer has done before
  2. Flag novel unit types/feature combos for a given detailer
  3. Power filtering in the UI

Typical description patterns:
    O)2 8X8X13 PP SPPP/LAU
    I)3 YC 12X8X24 PP FULLSEAM/316L-COMP/VFD/MMP/LAU
    65X124X358 MEDIUM
    RTF 9X9X18 AEROVENT/DURACOLD
    144X144X186, PRE-PAINT, NO ELECTRICAL
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# Regex for extracting dimension patterns like 8X8X13, 10'4"X11X35, 130x162x422
DIMENSION_PATTERN = re.compile(
    r"(\d+(?:'\d+\")?(?:\.\d+)?)\s*[Xx]\s*(\d+(?:\.\d+)?)" +
    r"(?:\s*[Xx]\s*(\d+(?:\.\d+)?))?"
)

# Unit type prefixes — must be followed by whitespace or end-of-string
# Recognized: O)2, O2, O)3, I)2, I3, OA)2, OA2, OAI)2, OAI2
# Note: RTF is NOT included here — RTF's trailing number is the first dimension,
# not a revision number handled separately.
UNIT_TYPE_PATTERN = re.compile(
    r"^(O[AI]?|I)\s*\)?\s*(\d+)?"
)

# Special flags enclosed in asterisks like *PRE-PAINT*
FLAG_PATTERN = re.compile(r"\*([^*]+)\*")

# Pattern to split description into tokens by common separators
TOKEN_SEPARATOR = re.compile(r"[/,\s]+")

# Patterns to clean individual tokens
TRAILING_DASH = re.compile(r"-+$")
LEADING_DASH = re.compile(r"^-+")


@dataclass
class ParsedTags:
    """Structured tags extracted from a unit description."""
    
    unit_type: str = ""          # e.g. "O)2", "I)3", "RTF"
    dimensions: str = ""         # e.g. "8X8X13", "144X144X186"
    features: list[str] = field(default_factory=list)   # e.g. ["VFD", "UV", "TCF"]
    flags: list[str] = field(default_factory=list)      # e.g. ["PRE-PAINT"]
    
    @property
    def feature_set(self) -> frozenset[str]:
        return frozenset(self.features)
    
    @property
    def normalized_type(self) -> str:
        """Normalized unit type (e.g. 'O2', 'I3') for matching."""
        return self.unit_type.replace(")", "").replace(" ", "").upper()


# ─── Feature detection helpers ───────────────────────────────────────

# Features that should be kept as a single token (for compound names like "FLOOD TEST")
_COMPOUND_FEATURES: set[str] = {
    "FLOOD TEST", "FULL SEAM", "PLATE TO PLATE HX",
    "SEIS CERT", "AL BASE", "316L SS",
    "LEAK&DEFLECTION TEST",
    "LEAK & DEFLECTION TEST",
    "LEAK AND DEFLECTION TEST",
    "TEST-V SILICONE-FREE",
    "WT-L FLOOD TEST", "WT-LD FLOOD TEST",
    "316L-COMP/HUM/VFD", "EVERYTHING SS",
    "NO ELECTRICAL",
}


def _is_likely_dimension_token(token: str) -> bool:
    """Check if a token looks like a dimension fragment."""
    # Pure numbers
    if re.match(r"^\d+(?:\.\d+)?$", token):
        return True
    # Dimension-like patterns
    if re.match(r"^\d+[Xx]\d+", token):
        return True
    return False


def _clean_token(token: str) -> str | None:
    """Clean a single token, return None if it should be skipped."""
    token = token.strip()
    if not token:
        return None
    # Remove leading/trailing dashes
    token = TRAILING_DASH.sub("", token)
    token = LEADING_DASH.sub("", token)
    token = token.strip()
    if not token or len(token) < 2:
        return None
    if _is_likely_dimension_token(token):
        return None
    return token.upper()


def parse_description(description: str) -> ParsedTags:
    """Parse a unit description and extract structured tags.
    
    Args:
        description: The raw description string (e.g. ``O)2 8X8X13 PP SPPP/LAU``)
    
    Returns:
        A ``ParsedTags`` instance with extracted tags.
    """
    if not description or not description.strip():
        return ParsedTags()
    
    text = description.strip()
    tags = ParsedTags()
    
    # 1. Extract special flags (*FLAG*)
    for match in FLAG_PATTERN.finditer(text):
        flag = match.group(1).strip()
        tags.flags.append(flag)
    text = FLAG_PATTERN.sub("", text)
    
    # 2. Extract unit type prefix (e.g., O)2, I)3, OA)2, OAI2)
    #    Note: RTF is handled as a regular feature token, not a unit type.
    unit_match = UNIT_TYPE_PATTERN.match(text)
    if unit_match:
        prefix = unit_match.group(1) or ""
        revision = unit_match.group(2) or ""
        
        if revision:
            tags.unit_type = f"{prefix}){revision}"
            text = text[unit_match.end():].strip()
        else:
            # For single-letter prefix without revision (e.g. "I 8X8X13"),
            # check if next char is a digit (short form like "I2")
            remaining = text[unit_match.end():].strip()
            if remaining and remaining[0].isdigit():
                tags.unit_type = f"{prefix}){remaining[0]}"
                text = remaining[1:].strip()
            else:
                # Not a unit type, restore text
                text = text.strip()
    
    # Check for "RTF" as a standalone prefix (always a unit type)
    if text.upper().startswith("RTF") and (len(text) == 3 or not text[3].isalnum()):
        tags.unit_type = "RTF"
        text = text[3:].strip()
        # Remove any trailing revision number (the "9" in "RTF 9") — it's a dimension start
        if text and text[0].isdigit():
            # Peek ahead: if followed by "X" it's part of dimensions, not a revision
            parts = text.split(None, 1)
            if parts and parts[0].isdigit() and len(parts) > 1:
                text = text[len(parts[0]):].strip()
            elif parts and parts[0].isdigit():
                text = ""
                tags.unit_type = "RTF"  # Just "RTF" as the feature, no numeric suffix
    
    # 3. Extract dimensions
    dim_match = DIMENSION_PATTERN.search(text)
    if dim_match:
        dim_parts = [g for g in dim_match.groups() if g is not None]
        tags.dimensions = "X".join(dim_parts).upper()
    
    # 4. Extract features — tokenize remaining text
    # First, handle compound features that span multiple tokens
    text_upper = text.upper()
    for compound in _COMPOUND_FEATURES:
        if compound in text_upper:
            tags.features.append(compound)
            text_upper = text_upper.replace(compound, "", 1)
    
    # Tokenize the rest
    tokens = TOKEN_SEPARATOR.split(text_upper)
    features_seen: set[str] = set()
    for token in tokens:
        cleaned = _clean_token(token)
        if cleaned is None:
            continue
        if cleaned in features_seen:
            continue
        features_seen.add(cleaned)
        tags.features.append(cleaned)
    
    return tags


def get_features_from_description(description: str) -> frozenset[str]:
    """Quick helper: extract just the feature set from a description."""
    return parse_description(description).feature_set


# ── Detailer Experience Repository ───────────────────────────────────

@dataclass
class DetailerExperience:
    """Tracks what unit types and feature combinations a detailer has done.
    
    This is built from the entire unit list and can be used to flag
    novel assignments.
    """
    detailer: str
    unit_types: set[str] = field(default_factory=set)
    feature_sets: list[frozenset[str]] = field(default_factory=list)
    dimension_ranges: list[str] = field(default_factory=list)
    
    def has_done_unit_type(self, unit_type: str) -> bool:
        """Check if this detailer has done the given unit type before."""
        return unit_type.upper() in {t.upper() for t in self.unit_types}
    
    def has_done_features(self, features: frozenset[str]) -> bool:
        """Check if this detailer has done ALL of the given features before."""
        req_upper = {f.upper() for f in features}
        for fs in self.feature_sets:
            existing_upper = {f.upper() for f in fs}
            if req_upper.issubset(existing_upper):
                return True
        return False
    
    def has_done_any_feature(self, feature: str) -> bool:
        """Check if this detailer has ever used a specific feature."""
        f_upper = feature.upper()
        return any(f_upper in {x.upper() for x in fs} for fs in self.feature_sets)


class UnitTagRepository:
    """Builds and queries a repository of tag knowledge from all units.
    
    Usage:
        repo = UnitTagRepository(units)
        repo.is_novel_for_detailer(unit, "Brandon B")  # True if new type
    """
    
    def __init__(self, units: list | None = None):
        self._detailer_experience: dict[str, DetailerExperience] = {}
        self._all_tags: dict[str, ParsedTags] = {}    # com_number -> tags
        self._all_tag_counts: dict[str, int] = {}      # tag -> total count
        if units:
            self.build(units)
    
    def build(self, units: list) -> None:
        """Build the repository from a list of Unit objects."""
        from data.models import Unit
        
        self._detailer_experience.clear()
        self._all_tags.clear()
        self._all_tag_counts.clear()
        
        feature_counter: dict[str, int] = {}
        
        for unit in units:
            if not isinstance(unit, Unit):
                continue
            tags = parse_description(unit.description)
            self._all_tags[unit.com_number] = tags
            
            # Count feature occurrences
            for feat in tags.features:
                feature_counter[feat] = feature_counter.get(feat, 0) + 1
            
            # Track detailer experience
            detailer = unit.detailer
            if detailer and detailer not in ("— Unassigned —", ""):
                if detailer not in self._detailer_experience:
                    self._detailer_experience[detailer] = DetailerExperience(detailer=detailer)
                
                exp = self._detailer_experience[detailer]
                if tags.unit_type:
                    exp.unit_types.add(tags.normalized_type)
                if tags.features:
                    exp.feature_sets.append(frozenset(tags.features))
                if tags.dimensions:
                    exp.dimension_ranges.append(tags.dimensions)
        
        self._all_tag_counts = feature_counter
    
    def rebuild_for_detailer(self, units: list, detailer: str) -> None:
        """Rebuild experience for a single detailer (e.g. after reassignment).
        
        Args:
            units: All units (filtered for the given detailer inside).
            detailer: The detailer name to rebuild experience for.
        """
        from data.models import Unit
        if detailer not in self._detailer_experience:
            self._detailer_experience[detailer] = DetailerExperience(detailer=detailer)
        
        exp = DetailerExperience(detailer=detailer)
        for unit in units:
            if not isinstance(unit, Unit):
                continue
            if unit.detailer != detailer:
                continue
            tags = parse_description(unit.description)
            if tags.unit_type:
                exp.unit_types.add(tags.normalized_type)
            if tags.features:
                exp.feature_sets.append(frozenset(tags.features))
            if tags.dimensions:
                exp.dimension_ranges.append(tags.dimensions)
        self._detailer_experience[detailer] = exp
    
    def get_tags(self, com_number: str) -> ParsedTags:
        """Get parsed tags for a unit by COM number."""
        return self._all_tags.get(com_number, ParsedTags())
    
    def is_novel_for_detailer(self, unit, detailer: str | None = None) -> tuple[bool, list[str]]:
        """Check if a unit would be novel for the given detailer.
        
        Args:
            unit: A Unit object or a description string.
            detailer: The detailer name. If None, uses unit.detailer.
        
        Returns:
            Tuple of (is_novel, reasons) where reasons is a list of
            human-readable strings describing what's novel.
        """
        from data.models import Unit
        
        if not detailer:
            detailer = unit.detailer if isinstance(unit, Unit) else ""
        if not detailer or detailer == "— Unassigned —":
            return False, []
        
        # Parse tags
        if isinstance(unit, Unit) and unit.com_number in self._all_tags:
            tags = self._all_tags[unit.com_number]
        else:
            desc = unit.description if isinstance(unit, Unit) else unit
            tags = parse_description(desc)
            # Cache it if it's a Unit
            if isinstance(unit, Unit):
                self._all_tags[unit.com_number] = tags
        
        exp = self._detailer_experience.get(detailer)
        if exp is None:
            return True, ["No prior work found for this detailer"]
        
        reasons: list[str] = []
        
        # Check unit type novelty
        if tags.unit_type and not exp.has_done_unit_type(tags.normalized_type):
            reasons.append(f"New unit type: {tags.unit_type}")
        
        # Check individual feature novelty
        novel_features: list[str] = []
        for feat in tags.features:
            if not exp.has_done_any_feature(feat):
                novel_features.append(feat)
        if novel_features:
            reasons.append(f"New feature(s): {', '.join(novel_features)}")
        
        # Check feature combo novelty
        if tags.features and not exp.has_done_features(frozenset(tags.features)):
            reasons.append("New feature combination")
        
        return len(reasons) > 0, reasons
    
    def get_all_features(self) -> list[tuple[str, int]]:
        """Get all tracked features sorted by frequency (most common first)."""
        return sorted(
            self._all_tag_counts.items(),
            key=lambda x: (-x[1], x[0])
        )
    
    def get_detailer_experience(self, detailer: str) -> DetailerExperience | None:
        """Get the experience record for a detailer."""
        return self._detailer_experience.get(detailer)