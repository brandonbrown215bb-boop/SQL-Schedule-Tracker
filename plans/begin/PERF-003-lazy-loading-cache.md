# PERF-003: Lazy Loading & Caching Strategy

**Status**: Draft  
**Priority**: Medium  
**Effort**: S (5 days)  
**Depends on**: None  

---

## Problem Statement

Several computations are eager-loaded and recomputed unnecessarily:

| Computation | Current Behavior | Wasted Work |
|------------|-----------------|-------------|
| `unit_fingerprint()` | Computed for all units on every fingerprint call | Cache keyed by com_number but no TTL/eviction |
| `parse_description()` | Called eagerly for all 2765 units on load | Only used if user views tags column or alert panel |
| `UnitTagRepository.build()` | Full rebuild on every load | 2765 descriptions parsed; most never viewed |
| `_apply_identicals()` | Runs on every load, full group recompute | Identical groups rarely change |
| `calculated_status_color` | Recalculated on every property access | No memoization per save cycle |

---

## Solution

Three-tier caching strategy:

1. **LRU Cache with TTL** — for fingerprints and tag-parsed results
2. **Lazy evaluation** — defer tag parsing to first access
3. **Background pre-computation** — compute aggregations after initial render

### Cache Architecture

```python
# services/cache.py

import time
from collections import OrderedDict
from typing import Any, Callable, TypeVar

T = TypeVar('T')


class TTLLRUCache:
    """LRU cache with time-to-live eviction.
    
    Items are evicted when:
    1. Cache size exceeds max_size (LRU eviction)
    2. Item age exceeds ttl_seconds (TTL eviction)
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, tuple[float, Any]] = OrderedDict()
    
    def get(self, key: str) -> Any | None:
        if key not in self._cache:
            return None
        timestamp, value = self._cache[key]
        if time.monotonic() - timestamp > self._ttl:
            del self._cache[key]
            return None
        self._cache.move_to_end(key)
        return value
    
    def set(self, key: str, value: Any) -> None:
        while len(self._cache) >= self._max_size:
            self._cache.popitem(last=False)
        self._cache[key] = (time.monotonic(), value)
    
    def invalidate(self, key: str) -> None:
        self._cache.pop(key, None)
    
    def invalidate_all(self) -> None:
        self._cache.clear()
    
    @property
    def size(self) -> int:
        return len(self._cache)


# Global cache instances
fingerprint_cache = TTLLRUCache(max_size=5000, ttl_seconds=600)
tag_parse_cache = TTLLRUCache(max_size=5000, ttl_seconds=600)


def cached_fingerprint(unit) -> str:
    """Cached wrapper around unit_fingerprint with TTL."""
    key = unit.com_number
    cached = fingerprint_cache.get(key)
    if cached is not None:
        return cached
    from data.loader import unit_fingerprint
    result = unit_fingerprint(unit)
    fingerprint_cache.set(key, result)
    return result


def cached_parse_description(com_number: str, description: str) -> "ParsedTags":
    """Lazy tag parsing with cache."""
    cached = tag_parse_cache.get(com_number)
    if cached is not None:
        return cached
    from data.tag_parser import parse_description
    result = parse_description(description)
    tag_parse_cache.set(com_number, result)
    return result
```

### Integration Points

```python
# data/loader.py — replace direct hash with cache-aware version
def unit_fingerprint(unit: Unit) -> str:
    # Keep existing logic, but callers can use cached_fingerprint
    ...

# In UnitTagRepository.build() — defer parsing
class UnitTagRepository:
    def build(self, units: list) -> None:
        # DON'T parse all descriptions eagerly
        # Just store unit references; parse on demand
        self._units = {u.com_number: u for u in units}
        self._tag_cache = {}  # populated on first access
    
    def get_tags(self, com_number: str) -> ParsedTags:
        if com_number not in self._tag_cache:
            unit = self._units.get(com_number)
            if unit:
                self._tag_cache[com_number] = parse_description(unit.description)
            else:
                return ParsedTags()
        return self._tag_cache[com_number]
    
    def is_novel_for_detailer(self, unit, detailer: str | None = None):
        # Only parse this one unit's tags, not all units
        tags = self.get_tags(unit.com_number)
        ...
```

### Fingerprint Cache Invalidation

```python
# In writer.py / UnitService.save() — invalidate on write
def save_unit(db_path: str, unit: Unit) -> None:
    # Invalidate caches for this COM number
    fingerprint_cache.invalidate(unit.com_number)
    tag_parse_cache.invalidate(unit.com_number)
    # ... existing save logic ...
```

### User-Configurable Cache Settings

```yaml
# config.yaml additions
performance:
  cache:
    fingerprint_ttl: 600         # seconds (10 min)
    fingerprint_max_size: 5000
    tag_parse_ttl: 600
    tag_parse_max_size: 5000
```

---

## Implementation Phases

### Phase 1: TTLLRUCache + Fingerprint Caching (2 days)
1. Implement `TTLLRUCache` class
2. Create global `fingerprint_cache` instance
3. Add `cached_fingerprint()` function
4. Replace all `unit_fingerprint()` calls with `cached_fingerprint()` in hot paths (loader, list panel diff)
5. Add invalidation in writer.py
6. **Tests**: Test cache hit/miss, TTL expiry, LRU eviction, invalidation

### Phase 2: Lazy Tag Parsing (2 days)
1. Refactor `UnitTagRepository.build()` to defer parsing
2. Store unit references, parse on first `get_tags()` call
3. Add `tag_parse_cache` with invalidation
4. **Tests**: Test lazy parsing, verify cache hit after first access

### Phase 3: Background Pre-computation (1 day)
1. After `_on_load_finished()`, schedule background computation of aggregations
2. Use `QTimer.singleShot(0, ...)` to defer to next event loop iteration
3. **Tests**: Verify aggregations are computed before user interacts with alert panel

---

## Success Criteria

1. Tag parsing on initial load: 2765 descriptions → 0ms (deferred)
2. Fingerprint computation: 0ms on first access (cached)
3. Cache hit rate > 90% during normal use
4. No stale data served after unit save (invalidation works)
5. Memory: cache stays under 50MB for 10,000 units

---

## Effort Estimate

| Phase | Days |
|-------|------|
| Phase 1: LRU Cache + Fingerprints | 2 |
| Phase 2: Lazy Tag Parsing | 2 |
| Phase 3: Background Pre-computation | 1 |
| **Total** | **5** |