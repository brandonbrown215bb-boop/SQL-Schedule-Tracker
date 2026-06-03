"""Tests for data/tag_parser.py"""
from data.tag_parser import parse_description, UnitTagRepository, ParsedTags


def test_empty_description():
    tags = parse_description("")
    assert tags.unit_type == ""
    assert tags.dimensions == ""
    assert tags.features == []
    assert tags.flags == []

    tags = parse_description(None)  # type: ignore
    assert tags.unit_type == ""


def test_basic_unit_type():
    tags = parse_description("O)2 8X8X13 PP SPPP/LAU")
    assert tags.unit_type == "O)2"
    assert tags.dimensions == "8X8X13"
    assert "VFD" not in tags.features  # VFD not in this one
    assert "SPPP" in tags.features
    assert "LAU" in tags.features
    assert "PP" in tags.features


def test_indoor_unit():
    tags = parse_description("I)3 YC 12X8X24 PP FULLSEAM/316L-COMP/VFD/MMP/LAU")
    assert tags.unit_type == "I)3"
    assert tags.dimensions == "12X8X24"
    assert "VFD" in tags.features
    assert "FULLSEAM" in tags.features or "FULL SEAM" in tags.features
    assert "MMP" in tags.features


def test_no_unit_type_prefix():
    """Some descriptions don't have a unit type prefix (e.g. MEDIUM, FLOW)."""
    tags = parse_description("65X124X358 MEDIUM")
    assert tags.unit_type == ""
    assert tags.dimensions == "65X124X358"
    assert "MEDIUM" in tags.features

    tags = parse_description("36X56X184 FLOW")
    assert tags.unit_type == ""
    assert tags.dimensions == "36X56X184"
    assert "FLOW" in tags.features


def test_rtf_unit():
    tags = parse_description("RTF 9X9X18 AEROVENT/DURACOLD")
    assert tags.unit_type == "RTF"
    assert tags.dimensions == "9X9X18"
    assert "AEROVENT" in tags.features
    assert "DURACOLD" in tags.features


def test_flags():
    tags = parse_description("144X144X186, PRE-PAINT, NO ELECTRICAL")
    assert tags.dimensions == "144X144X186"
    assert "PRE-PAINT" in tags.features

    tags = parse_description("261731 144X156X412 *LEAK&DEFLECTION TEST")
    # Without closing * the pattern is not a flag — it becomes a feature
    # With proper closing *, it goes into flags
    assert "LEAK&DEFLECTION TEST" in tags.features or "LEAK&DEFLECTION TEST" in tags.flags
    assert tags.dimensions == "144X156X412"

    # Properly closed asterisk flags should go into flags
    tags = parse_description("144X156X412 *SPECIAL-FLAG*")
    assert "SPECIAL-FLAG" in tags.flags


def test_trailing_dash():
    tags = parse_description("O)3 13X21X39 PP HIGH-PIPE-HOURS/TEST-VIB/VEST/DRC-")
    assert tags.unit_type == "O)3"
    assert tags.dimensions == "13X21X39"
    # DRC- should be cleaned to DRC
    assert "DRC" in tags.features
    assert "HIGH-PIPE-HOURS" in tags.features


def test_compound_features():
    tags = parse_description("O)4 10X14X31 TEST-LD/FLOOD TEST/SS HOUSING/UV/CS-V")
    assert tags.unit_type == "O)4"
    assert "FLOOD TEST" in tags.features
    assert "TEST-LD" in tags.features


def test_short_description():
    tags = parse_description("134x145x270")
    assert tags.dimensions == "134X145X270"
    assert tags.features == []
    assert tags.unit_type == ""


def test_feature_set():
    tags = parse_description("O)2 8X8X13 PP SPPP/LAU")
    fset = tags.feature_set
    assert isinstance(fset, frozenset)
    assert "SPPP" in fset
    assert "LAU" in fset
    assert "PP" in fset
    assert len(fset) == 3


def test_normalized_type():
    tags = parse_description("O)2 8X8X13 PP SPPP/LAU")
    assert tags.normalized_type == "O2"
    
    tags = parse_description("I)3 YC 12X8X24 PP VFD")
    assert tags.normalized_type == "I3"


def test_global_feature_counts():
    """Test that all features are properly counted across units."""
    # Build repository with a few sample units
    from data.models import Unit
    
    units = [
        Unit(com_number="1", job_name="", contract_number="", 
             description="O)2 8X8X13 PP SPPP/LAU", detailer="Test D",
             checking_status=""),
        Unit(com_number="2", job_name="", contract_number="",
             description="I)3 YC 12X8X24 PP VFD/MMP/LAU", detailer="Test D",
             checking_status=""),
        Unit(com_number="3", job_name="", contract_number="",
             description="O)2 10X10X10 PP SPPP/LAU/VFD", detailer="Test D",
             checking_status=""),
    ]
    
    repo = UnitTagRepository(units)
    
    # Check feature counts
    features = repo.get_all_features()
    feature_dict = {name: count for name, count in features}
    
    assert feature_dict.get("LAU", 0) == 3  # present in all 3
    assert feature_dict.get("SPPP", 0) == 2
    assert feature_dict.get("VFD", 0) == 2
    assert feature_dict.get("PP", 0) == 3  # present in all 3


def test_novelty_detection():
    from data.models import Unit
    
    # Detailer has done O)2 with SPPP/LAU, now gets I)3 with full feature set
    units = [
        Unit(com_number="1", job_name="", contract_number="",
             description="O)2 8X8X13 PP SPPP/LAU", detailer="Test D", 
             checking_status=""),
        Unit(com_number="2", job_name="", contract_number="",
             description="O)2 10X10X10 PP SPPP/LAU/VFD", detailer="Test D",
             checking_status=""),
    ]
    
    repo = UnitTagRepository(units)
    
    # Same type, same features — not novel
    unit = Unit(com_number="3", job_name="", contract_number="",
                description="O)2 12X12X12 PP SPPP/LAU/VFD", detailer="Test D",
                checking_status="")
    is_novel, reasons = repo.is_novel_for_detailer(unit, "Test D")
    assert not is_novel  # O)2 type and features are all known
    
    # New unit type
    unit = Unit(com_number="4", job_name="", contract_number="",
                description="I)3 12X8X24 PP VFD/MMP/LAU", detailer="Test D",
                checking_status="")
    is_novel, reasons = repo.is_novel_for_detailer(unit, "Test D")
    assert is_novel
    assert any("unit type" in r.lower() for r in reasons)
    
    # New feature
    unit = Unit(com_number="5", job_name="", contract_number="",
                description="O)2 8X8X13 PP SPPP/NEWFEATURE", detailer="Test D",
                checking_status="")
    is_novel, reasons = repo.is_novel_for_detailer(unit, "Test D")
    assert is_novel
    assert any("NEWFEATURE" in r for r in reasons)


def test_unassigned_detailer():
    from data.models import Unit
    
    units = [
        Unit(com_number="1", job_name="", contract_number="",
             description="O)2 8X8X13 PP SPPP/LAU", detailer="— Unassigned —",
             checking_status=""),
    ]
    repo = UnitTagRepository(units)
    
    unit = Unit(com_number="2", job_name="", contract_number="",
                description="O)2 8X8X13 PP SPPP/LAU", detailer="— Unassigned —",
                checking_status="")
    is_novel, reasons = repo.is_novel_for_detailer(unit)
    assert not is_novel  # Unassigned detailers are skipped


if __name__ == "__main__":
    # Run tests with simple assertions
    test_empty_description()
    print("✓ test_empty_description")
    test_basic_unit_type()
    print("✓ test_basic_unit_type")
    test_indoor_unit()
    print("✓ test_indoor_unit")
    test_no_unit_type_prefix()
    print("✓ test_no_unit_type_prefix")
    test_rtf_unit()
    print("✓ test_rtf_unit")
    test_flags()
    print("✓ test_flags")
    test_trailing_dash()
    print("✓ test_trailing_dash")
    test_compound_features()
    print("✓ test_compound_features")
    test_short_description()
    print("✓ test_short_description")
    test_feature_set()
    print("✓ test_feature_set")
    test_normalized_type()
    print("✓ test_normalized_type")
    test_global_feature_counts()
    print("✓ test_global_feature_counts")
    test_novelty_detection()
    print("✓ test_novelty_detection")
    test_unassigned_detailer()
    print("✓ test_unassigned_detailer")
    print("\nAll tests passed!")