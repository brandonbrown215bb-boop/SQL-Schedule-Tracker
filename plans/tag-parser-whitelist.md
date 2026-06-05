# Plan: Tag Parser Whitelist + Normalization

## Current State

- 2,758 units with descriptions parsed
- 800 unique features extracted (way too many — noise dominates)
- 13 unit types (these look mostly correct)
- Parser uses a blacklist approach (strip dimensions, strip short tokens) but no whitelist

## Problems Identified

### 1. Noise tokens (374 singletons, ~200 low-frequency)
- Dimension fragments leaked through: `10.5X20X34`, `9.5X14X34` (5 instances)
- Garbage from special chars: `#1`-`#11`, `(2")`, `(BOTTOM)`, `(QTY`, `(TOP)`, `**`, `**NO`, `*ENAMEL`, `*NO`
- Split compound features: `PLATE` + `TO` + `PLATE` instead of `PLATE TO PLATE HX`
- English words that aren't features: `ONLY`, `SOME`, `ALL`, `NO`, `UNIT`, `FOR`, `AND`, etc.
- Misspelled variants: `FULLS` vs `FULLSEAM`, `BISE` vs `BISEL`, `COMPLE` vs `COMPLETE`

### 2. Compound feature detection is incomplete
Only 11 compound features in `_COMPOUND_FEATURES`. Missing:
- `HEAT PIPE` (currently split into `HEAT` + `PIPE`)
- `CU FIN` / `CU FIN COIL` (split into `CU` + `FIN` + `COIL`)
- `FULL SEAM` (split, and variants like `FULLSEAM-1` through `FULLSEAM-10`)
- `SIDE BY SIDE` (split into `SIDE` + `SIDE`)
- `LEAK & DEFLECTION` / `LEAK AND DEFLECTION` (partially handled)
- `SS DIA PLATE` → `SS-DIAM-PLATE`
- `DEFENSE PRIORITY` / `DEF PRIORITY` (variants)
- `HIGH PIPE` / `HIGH PIPE HOURS` / `HIGH PIPE HRS` (variants)

### 3. Feature normalization missing
Same concept, different spellings:
- `WT-L`, `WT-LD`, `WT-LA`, `WT-LDA`, `WT-LDV`, `WT-LAV`, `WT-LDAV` — these are a family but that's fine (they're distinct)
- `FULLSEAM` vs `FULL SEAM` vs `FULLSEAM-1` vs `FULLSEAM-2` etc.
- `AL BASE` vs `AL-BASE` vs `ALBASE`
- `316L SS` vs `316LSS` vs `316SS`
- `TEST-L` vs `TEST-LD` vs `TEST-LDA` vs `TEST-LDV` vs `TEST-LAV` vs `TEST-L-D` vs `TEST-L-D-A`
- `VFD` vs `VFD(CS)` vs `VFD-FANS` vs `CS-VFD`
- `MMP` vs `MMP-BOTTOM` vs `MMP-TOP` vs `MMP-MOVE` vs `MMP-CS-EBTRON`
- `SPPP` vs `SPPP(CS)` vs `DRC-SPPP` vs `BISEL-SPPP`

### 4. RTF parsing is fragile
Only 11 RTF units. The current code strips a leading digit after "RTF" assuming it's a revision number, but `RTF 9X9X18` — the `9` is the first dimension. This actually works correctly in the samples I checked, but the code path is convoluted.

## Approach: Whitelist + Normalization Map

### Phase 1: Build the whitelist

Create a canonical feature list (~150-200 real features) from the high/mid-frequency tokens in tag_review.md, plus domain knowledge. Everything not in the whitelist gets dropped.

**Whitelist categories:**
- **Unit type markers**: VFD, MMP, PP, YC, LAU, SPPP, UV, TCF, VEST, HUM, NGH, MP, EBM, KDOWN, HWHL, COIL, PAINT, ALUM, FULLSEAM, TEX, SWRAP, FLOW, HX, SS, TUNNEL, BISEL, DUAL, TIG, HOUSING, EP, BASE, SA, WELD, SPP, AEROVENT, FLR, HEATCO, CAMFIL, TEST, STACK, BOX, TOP, BOTTOM, HOT, COLD, HIGH, LOW, LARGE, MEDIUM, SINGLE, TRIPLE, QUAD, FULL, PARTIAL, PRE, POST, NEW, RAW, COATED, GALV, AL, CU, CS, HW, WT, LD, LA, TC, DRC, FPC, HTR, AB, NOA, HSB, DEFENSE, PRIORITY, SEISMIC, WITNESS, LEAK, DEFLECTION, FLOOD, PLATE, HEAT, PIPE, FIN, COATED, EPOXY, ENAMEL, SILICONE, STAINLESS, STEEL, GALVANIZED, ALUMINUM, COPPER, etc.

### Phase 2: Build normalization map

Map variant spellings → canonical form:

```
"AL BASE" → "AL-BASE"
"ALBASE" → "AL-BASE"
"316L SS" → "316L-SS"
"316LSS" → "316L-SS"
"316SS" → "316L-SS"
"FULL SEAM" → "FULLSEAM"
"FULLSEAM-1" → "FULLSEAM"
"FULLSEAM-2" → "FULLSEAM"
... (all numbered variants)
"CU FIN" → "CU-FIN"
"CU FIN COIL" → "CU-FIN-COIL"
"HEAT PIPE" → "HEAT-PIPE"
"SIDE BY SIDE" → "SIDE-BY-SIDE"
"LEAK&DEFLECTION" → "LEAK-DEFLECTION"
"LEAK & DEFLECTION" → "LEAK-DEFLECTION"
"LEAK AND DEFLECTION" → "LEAK-DEFLECTION"
"PLATE TO PLATE" → "PLATE-TO-PLATE"
"PLATE TO PLATE HX" → "PLATE-TO-PLATE-HX"
"SS DIA PLATE" → "SS-DIAM-PLATE"
"DEF PRIORITY" → "DEFENSE-PRIORITY"
"HIGH PIPE" → "HIGH-PIPE"
"HIGH PIPE HOURS" → "HIGH-PIPE"
"HIGH PIPE HRS" → "HIGH-PIPE"
"CS-VFD" → "VFD"
"VFD(CS)" → "VFD"
"VFD-FANS" → "VFD"
"SPPP(CS)" → "SPPP"
"DRC-SPPP" → "SPPP"
"BISEL-SPPP" → "SPPP"
"MMP-BOTTOM" → "MMP"
"MMP-TOP" → "MMP"
"MMP-MOVE" → "MMP"
"MMP-CS-EBTRON" → "MMP"
"TEST-L-D" → "TEST-LD"
"TEST-L-D-A" → "TEST-LDAV"
"TEST-LDAV" → "TEST-LDAV"
"TEST-LAV" → "TEST-LAV"
```

### Phase 3: Rewrite parser

1. Pre-compound: match multi-word compounds first (longest match first)
2. Extract unit type (existing logic, mostly correct)
3. Extract dimensions (existing logic, fix edge cases)
4. Tokenize remaining text
5. For each token: look up in whitelist → keep; look up in normalization map → normalize; else → drop
6. Deduplicate

### Phase 4: Update `_COMPOUND_FEATURES`

Expand to cover all multi-word features found in the data.

## Files Changed

| File | Change |
|------|--------|
| `data/tag_parser.py` | Add `FEATURE_WHITELIST` set, `FEATURE_NORMALIZATION` dict, rewrite `parse_description()` |
| `data/tag_parser.py` | Expand `_COMPOUND_FEATURES` to ~30+ entries |

## Verification

1. Run parser against all 2,758 descriptions
2. Verify: 800 unique features → ~150-200 canonical features
3. Verify: no dimension fragments in features
4. Verify: no garbage tokens (#, *, parens)
5. Verify: compound features preserved (HEAT-PIPE, FULLSEAM, etc.)
6. Verify: unit types still correct (13 types, same distribution)
7. Spot-check 20 random descriptions manually

## Open Questions

1. Should `WT-LD`, `WT-LA`, `WT-LDA` etc. be normalized to a family (`WT-L*`) or kept distinct? They seem like distinct test types.
2. Should `SPPP(CS)` normalize to `SPPP` or keep the `(CS)` qualifier? The CS might mean "controls" which is meaningful.
3. What's the threshold for whitelist inclusion? Features appearing ≥2 times? ≥5?
