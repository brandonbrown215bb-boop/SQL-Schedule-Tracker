# QA-001: Property-Based Testing with Hypothesis

**Status**: Draft  
**Priority**: Medium  
**Effort**: M (8 days)  
**Depends on**: ARCH-003  
**Partners**: QA-002, QA-003  

---

## Problem Statement

Current tests use example-based testing (hardcoded inputs → expected outputs). This approach:

- **Misses edge cases** — tests only cover the inputs the author thought of
- **Brittle** — a single behavior change breaks dozens of example-based assertions
- **No invariants** — never tests that "for ANY valid unit, `calculated_status_color` returns one of 6 colors"
- **Low coverage** — combinatorial explosion of field combinations is untested
- **No roundtrip tests** — serialization (Unit → DB → Unit) fidelity is never verified

---

## Proposed Solution

Use Hypothesis for property-based testing. Define strategies (data generators) for `Unit` fields, then write property tests that assert invariants across thousands of random inputs.

### Architecture

```
tests/
├── property/
│   ├── __init__.py
│   ├── conftest.py           # Shared Hypothesis profiles, custom strategies
│   ├── strategies.py         # Unit generation strategies
│   ├── test_model_props.py   # calculated_status_color, alert_level, is_stale
│   ├── test_loader_props.py  # fingerprint, identicals, roundtrip
│   ├── test_tag_parser_props.py  # parse_description, idempotency
│   └── test_import_props.py  # CSV roundtrip
```

### Custom Strategies

```python
# tests/property/strategies.py

from datetime import date, timedelta
from hypothesis import strategies as st

from data.models import Unit, StatusColor

# Status colors
status_colors = st.sampled_from(["gray", "yellow", "purple", "orange", "green", "red"])

# Detailer names
detailer_names = st.sampled_from([
    "Jackie H", "Tommy N", "Matthew S", "Matthew E", "Carl M",
    "Stewart D", "David K", "Katie D", "Kris L", "Emilio P",
    "Timothy B", "Jeremy B", "Brandon B", "Tracy V", "Tanner D",
    "— Unassigned —",
])

# COM numbers (4-6 digit strings)
com_numbers = st.text(
    alphabet=st.characters(whitelist_categories=["Nd"]),  # digits only
    min_size=4, max_size=6,
)

# Dates (within a reasonable range for schedule data)
def date_between(min_offset: int = -365, max_offset: int = 365) -> st.SearchStrategy[date]:
    """Generate dates within offset days from today."""
    today = date.today()
    min_date = today + timedelta(days=min_offset)
    max_date = today + timedelta(days=max_offset)
    return st.dates(min_value=min_date, max_value=max_date)


def unit_strategy(
    with_contract_number: bool = True,
    with_due_date: bool = True,
    percent_range: tuple[float, float] = (0.0, 100.0),
) -> st.SearchStrategy:
    """Generate a valid Unit with randomized fields.
    
    Args:
        with_contract_number: Include contract_number (for identicals testing)
        with_due_date: Include detailing_due_date (not all units have one)
        percent_range: Range for percent_complete (default 0-100)
    """
    return st.builds(
        Unit,
        com_number=com_numbers,
        job_name=st.text(max_size=50).filter(bool),
        contract_number=com_numbers if with_contract_number else st.just(""),
        description=st.text(max_size=200).filter(lambda s: not s or len(s) > 0),
        detailer=detailer_names,
        checking_status=st.text(max_size=30),
        notes=st.text(max_size=100) | st.none(),
        status_color=status_colors,
        department_hours=st.floats(min_value=0, max_value=500, allow_nan=False),
        target_department_hours=st.floats(min_value=0, max_value=500, allow_nan=False),
        iec_internal_hours=st.floats(min_value=0, max_value=200, allow_nan=False),
        percent_complete=st.floats(
            min_value=percent_range[0],
            max_value=percent_range[1],
            allow_nan=False,
        ),
        actual_hours=st.floats(min_value=0, max_value=500, allow_nan=False),
        unit_detailing_start_date=date_between(-30, 90) | st.none(),
        unit_moved_to_checking_date=date_between(-30, 90) | st.none(),
        unit_detailing_completion_date=date_between(-30, 90) | st.none(),
        detailing_due_date=date_between(-30, 90) if with_due_date else st.none(),
        dept_due_date_previous=date_between(-60, 0) | st.none(),
        build_date=date_between(-90, -1) | st.none(),
        working_days=st.lists(
            st.integers(min_value=0, max_value=4),
            min_size=1, max_size=5,
            unique=True,
        ) | st.none(),
    )


def invalid_unit_strategy() -> st.SearchStrategy:
    """Generate an intentionally INVALID Unit for validation testing."""
    return st.builds(
        Unit,
        com_number=st.text(min_size=0, max_size=20),  # may be empty or invalid
        job_name=st.text(max_size=255),
        contract_number=st.text(max_size=50),
        description=st.text(max_size=500),
        detailer=st.text(max_size=100),  # any string, not just valid names
        percent_complete=st.floats(min_value=-100, max_value=200, allow_nan=True),
        department_hours=st.floats(min_value=-100, allow_nan=True),
        status_color=st.text(),  # any string, not just valid colors
        detailing_due_date=date_between(-365, 365) | st.none(),
        unit_detailing_start_date=date_between(-365, 365) | st.none(),
    )
```

### Property Tests

```python
# tests/property/test_model_props.py

from datetime import date
from hypothesis import given, assume, settings
from data.models import Unit, _working_days_between

from tests.property.strategies import unit_strategy


@given(unit_strategy())
@settings(max_examples=1000)
def test_calculated_status_color_is_always_valid(unit: Unit):
    """For ANY valid Unit, calculated_status_color must be one of 6 colors."""
    color = unit.calculated_status_color
    assert color in ("gray", "yellow", "purple", "orange", "green", "red"), f"Got {color}"


@given(unit_strategy(percent_range=(100.0, 100.0)))
@settings(max_examples=100)
def test_calculated_status_color_green_at_100_percent(unit: Unit):
    """At 100% complete, status is always green regardless of other fields."""
    assert unit.calculated_status_color == "green"


@given(unit_strategy())
@settings(max_examples=500)
def test_alert_level_is_always_valid(unit: Unit):
    """For ANY valid Unit, alert_level must be one of 6 levels."""
    level = unit.alert_level
    assert level in ("COMPLETE", "UNSET", "OVERDUE", "URGENT", "APPROACHING", "ON_TRACK")


@given(
    unit_strategy(percent_range=(100.0, 100.0)),
)
@settings(max_examples=100)
def test_alert_level_complete_at_100_percent(unit: Unit):
    assert unit.alert_level == "COMPLETE", f"100% unit got alert_level={unit.alert_level}"


@given(unit_strategy(with_due_date=True))
@settings(max_examples=500)
def test_is_stale_consistency(unit: Unit):
    """is_stale must be True when due date > 30 days in the past."""
    from data.models import STALE_THRESHOLD_DAYS
    from datetime import timedelta
    
    if unit.detailing_due_date:
        days_old = (date.today() - unit.detailing_due_date).days
        if days_old > STALE_THRESHOLD_DAYS:
            assert unit.is_stale
        else:
            assert not unit.is_stale


@given(
    st.datetimes().map(lambda dt: dt.date()),
    st.datetimes().map(lambda dt: dt.date()),
)
@settings(max_examples=500)
def test_working_days_between_bounds(start: date, end: date):
    """_working_days_between result must be 0 <= result <= days between dates."""
    assume(start <= end)
    result = _working_days_between(start, end)
    calendar_days = (end - start).days
    assert 0 <= result <= calendar_days, f"{start} -> {end}: got {result}"
```

```python
# tests/property/test_loader_props.py

from hypothesis import given, assume, settings
from hypothesis import strategies as st

from data.loader import unit_fingerprint, _apply_identicals
from tests.property.strategies import unit_strategy, com_numbers


@given(unit_strategy(with_contract_number=True))
@settings(max_examples=1000)
def test_fingerprint_is_stable(unit):
    """Same unit object -> same fingerprint always."""
    fp1 = unit_fingerprint(unit)
    fp2 = unit_fingerprint(unit)
    assert fp1 == fp2
    assert len(fp1) == 16  # sha256 truncated to 16 chars


@given(
    unit_strategy(with_contract_number=True),
    unit_strategy(with_contract_number=True),
)
@settings(max_examples=500)
def test_different_units_different_fingerprints(unit_a, unit_b):
    """Different com_number -> different fingerprint."""
    assume(unit_a.com_number != unit_b.com_number)
    fp_a = unit_fingerprint(unit_a)
    fp_b = unit_fingerprint(unit_b)
    assert fp_a != fp_b, f"Collision: {unit_a.com_number} == {unit_b.com_number}"


@given(
    st.lists(unit_strategy(with_contract_number=True), min_size=1, max_size=50),
)
@settings(max_examples=200)
def test_apply_identicals_non_primary_have_zero_target(units):
    """After _apply_identicals, non-primary identicals have target=0."""
    from collections import Counter
    
    _apply_identicals(units)
    
    # Group by contract_number
    groups = {}
    for u in units:
        key = u.contract_number
        if key:
            groups.setdefault(key, []).append(u)
    
    for contract, group in groups.items():
        if len(group) >= 2:
            non_primary = [u for u in group if u.is_non_primary_identical]
            for u in non_primary:
                assert u.target_department_hours == 0.0, \
                    f"COM {u.com_number} (non-primary identical) has target={u.target_department_hours}"


@given(unit_strategy(with_contract_number=False))
@settings(max_examples=200)
def test_apply_identicals_no_contract_number_untouched(unit):
    """Units without contract_number are not affected by identicals."""
    _apply_identicals([unit])
    assert not unit.is_non_primary_identical
    # target_department_hours stays as set
```

```python
# tests/property/test_tag_parser_props.py

from hypothesis import given, settings
from hypothesis import strategies as st

from data.tag_parser import parse_description


@given(st.text())
@settings(max_examples=2000)
def test_parse_never_crashes(description: str):
    """Any string input must not crash the parser."""
    result = parse_description(description)
    # Must return a ParsedTags (even if empty)
    assert result is not None


@given(st.text())
@settings(max_examples=1000)
def test_parse_output_is_consistent(result):
    """parse_description must be deterministic."""
    r1 = parse_description(result)
    r2 = parse_description(result)
    assert r1.unit_type == r2.unit_type
    assert r1.dimensions == r2.dimensions
    assert r1.features == r2.features
    assert r1.flags == r2.flags


@given(st.text(max_size=50).filter(lambda s: "*" in s))
@settings(max_examples=500)
def test_flags_preserved(description: str):
    """Asterisk-enclosed tokens must be extracted as flags."""
    result = parse_description(description)
    if "*" in description:
        # At least one flag should be found
        assert len(result.flags) >= 0  # at minimum, no crash
```

---

## Implementation Phases

### Phase 1: Hypothesis Setup + Unit Strategies (2 days)
1. Install Hypothesis: `pip install hypothesis`
2. Create `tests/property/strategies.py` with `unit_strategy()` and `invalid_unit_strategy()`
3. Create `tests/property/conftest.py` with Hypothesis profile settings
4. Write initial smoke test: "parse any description never crashes"
5. **Tests**: Verify strategies generate valid outputs; run with `--hypothesis-show-statistics`

### Phase 2: Model Properties (2 days)
1. Implement `test_calculated_status_color_is_always_valid`
2. Implement `test_alert_level_is_always_valid`, `test_is_stale_consistency`
3. Implement `test_working_days_between_bounds`
4. Run with 5000 examples each; verify no failures

### Phase 3: Tag Parser Properties (2 days)
1. Implement `test_parse_never_crashes` with 2000 random strings
2. Implement idempotency test (parse → reconstruct → parse)
3. Implement feature whitelist invariant: all parsed features are in `_WHITELIST`
4. **Tests**: Run against the 2765 production descriptions as seed corpus

### Phase 4: Import/Export Properties (2 days)
1. Implement `test_fingerprint_stable`, `test_different_units_different_fingerprints`
2. Implement `test_apply_identicals_non_primary_have_zero_target`
3. Implement CSV roundtrip property: generate Unit → serialize to CSV row → parse → verify fields preserved
4. **Tests**: Verify all properties pass with 1000+ examples each

---

## Success Criteria

1. 15+ property tests covering all major invariants
2. Each test runs 1000+ examples by default
3. Zero failures in CI for all property tests
4. Coverage identifies at least one previously unknown edge case
5. Strategies generate valid Units that match real data distribution

---

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Hypothesis slow in CI | Medium | Use smaller example counts in CI; full suite nightly |
| Strategies produce unrealistic data | Medium | Use production data analysis to tune strategy distributions |
| Property too weak (false pass) | Low | Combine multiple properties per invariant; use `.filter()` and `.assume()` |
| Flaky tests from date-dependent properties | Low | Freeze dates in conftest; use `freezegun` |

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: Setup + Strategies | 2 |
| Phase 2: Model Properties | 2 |
| Phase 3: Tag Parser Properties | 2 |
| Phase 4: Import/Export Properties | 2 |
| **Total** | **8** |