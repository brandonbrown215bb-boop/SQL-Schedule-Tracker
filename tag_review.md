# Tag Parser Review — Feature Audit

**Generated:** 2026-06-03
**Source:** 2,765 units from `schedule.db`
**Total unique features extracted:** 800

## Instructions

Review each section below. For the **Candidate Blacklist**, mark tokens you want to **keep** (i.e., they are meaningful features). Everything unmarked will be blacklisted.

Return the marked-up file or a list of kept tokens and we'll build the whitelist + normalization map.

---

## Unit Types (13 total)

These are extracted by the unit type regex. Review for correctness.

| Type | Notes |
|------|-------|
| `I)2` | |
| `I)3` | |
| `I)4` | |
| `I)9` | |
| `I)13` | |
| `I)25` | |
| `O)2` | |
| `O)3` | |
| `O)4` | |
| `OA)2` | |
| `OA)3` | |
| `OA)10` | |
| `RTF` | |

---

## High-Frequency Features (≥ 50 occurrences)

These are almost certainly real features. Review for any that should be blacklisted.

| Count | Feature | Keep? |
|-------|---------|-------|
| 933 | `VFD` | |
| 806 | `MMP` | |
| 710 | `PP` | |
| 663 | `YC` | |
| 598 | `LAU` | |
| 579 | `SPPP` | |
| 382 | `UV` | |
| 372 | `TCF` | |
| 236 | `VEST` | |
| 206 | `HUM` | |
| 197 | `NGH` | |
| 163 | `TIER` | |
| 139 | `MP` | |
| 127 | `EBM` | |
| 120 | `KDOWN` | |
| 117 | `HWHL` | |
| 107 | `COIL` | |
| 99 | `WT-LD` | |
| 94 | `PAINT` | |
| 91 | `AL-BASE` | |
| 90 | `ALUM` | |
| 89 | `FULLSEAM` | |
| 88 | `WT-L` | |
| 87 | `TEST-LD` | |
| 85 | `HW` | |
| 85 | `SEIS-CERT` | |
| 82 | `TEX` | |
| 82 | `TEX-AL` | |
| 75 | `SWRAP` | |
| 72 | `FLOW` | |
| 72 | `TEX-AL-WALL` | |
| 69 | `GENESIS` | |
| 69 | `HX` | |
| 64 | `SS` | |
| 64 | `TUNNEL` | |
| 63 | `BISEL` | |
| 63 | `DUAL` | |
| 59 | `WT-LDA` | |
| 55 | `TIG` | |
| 54 | `HOUSING` | |
| 53 | `E-FIN-COIL` | |
| 52 | `EP` | |
| 49 | `MEDIUM` | |
| 47 | `PRE-PAINT` | |
| 45 | `BASE` | |
| 42 | `SA` | |
| 40 | `SPP` | |
| 40 | `WELD` | |
| 39 | `AEROVENT` | |
| 38 | `FLR` | |
| 36 | `E-FIN` | |
| 36 | `HEATCO` | |
| 35 | `CAMFIL` | |
| 35 | `TEST-V` | |
| 34 | `STITCH` | |
| 33 | `DEF-PRIORITY` | |
| 33 | `OBO` | |
| 33 | `PLATE` | |

---

## Mid-Frequency Features (10–49 occurrences)

Review these — mix of real features and noise.

| Count | Feature | Keep? |
|-------|---------|-------|
| 32 | `NO` | |
| 31 | `DIA` | |
| 31 | `TEST-LDA` | |
| 30 | `COILS` | |
| 30 | `CS-VFD` | |
| 30 | `DRC` | |
| 30 | `SEISMIC` | |
| 30 | `TEST-D` | |
| 30 | `TOP` | |
| 29 | `CS` | |
| 29 | `CU` | |
| 29 | `TC` | |
| 28 | `ABB-VFD` | |
| 27 | `AL BASE` | |
| 27 | `COATED` | |
| 27 | `CU-FIN-COIL` | |
| 27 | `DEFENSE-PRIORITY` | |
| 27 | `FPC` | |
| 27 | `HERESITE-COIL` | |
| 27 | `HTR` | |
| 25 | `AEROFIN` | |
| 25 | `CHEMBIO` | |
| 25 | `FIN` | |
| 23 | `HIGH-PIPE` | |
| 23 | `TEST-L` | |
| 23 | `WITNESS` | |
| 22 | `HSB` | |
| 22 | `TEST` | |
| 21 | `CS-CONTROLS` | |
| 21 | `ELEC` | |
| 21 | `FLOOD TEST` | |
| 21 | `NOA` | |
| 20 | `AB` | |
| 20 | `BOX` | |
| 20 | `ELECTROFIN` | |
| 20 | `FULLSEAM-3` | |
| 20 | `TEST-LDV` | |
| 20 | `TEST-VIB` | |
| 19 | `316L SS` | |
| 19 | `STACK-W` | |
| 19 | `TAMCO` | |
| 18 | `316L` | |
| 18 | `ABB` | |
| 18 | `DIP` | |
| 18 | `L&D` | |
| 18 | `WING` | |
| 17 | `DISC` | |
| 17 | `HIGH-PIPE-HOURS` | |
| 17 | `HIGH-PIPE-HRS` | |
| 17 | `LARGE` | |
| 17 | `TO` | |
| 16 | `316L-COMP` | |
| 16 | `FULLSE` | |
| 16 | `INDECCO` | |
| 16 | `MODINE` | |
| 16 | `TESTING` | |
| 16 | `VIBRATION` | |
| 15 | `COAT` | |
| 15 | `CS-HUM` | |
| 15 | `CS-VRF-KIT` | |
| 15 | `DTM` | |
| 15 | `PICKING` | |
| 15 | `PIPE-HRS` | |
| 14 | `BISEL-SPPP` | |
| 14 | `CS-EBTRON` | |
| 14 | `SEIS` | |
| 14 | `TEX-AL-WALLS` | |
| 14 | `WING-COIL` | |
| 13 | `316L-COMP/HUM/VFD` | |
| 13 | `BOTTOM` | |
| 13 | `HOT` | |
| 13 | `HPIPE` | |
| 13 | `TEST-A` | |
| 12 | `HERESITE` | |
| 12 | `LEAK` | |
| 12 | `TEST-V SILICONE-FREE` | |
| 11 | `ABASE` | |
| 11 | `AIRFLOW` | |
| 11 | `BASE-16G-G90` | |
| 11 | `CS-V` | |
| 11 | `DURACOLD` | |
| 11 | `MILLER` | |
| 11 | `SILICONE-FREE` | |
| 11 | `T-A` | |
| 11 | `UNIT` | |
| 11 | `UTB` | |
| 10 | `COILMASTER` | |
| 10 | `E-COATED` | |
| 10 | `GENESIS-SC` | |
| 10 | `K-DOWN` | |
| 10 | `L-D` | |
| 10 | `MM` | |
| 10 | `PRE` | |
| 10 | `SIDEXSIDE-TUNNELS` | |
| 10 | `STACKED` | |

---

## Low-Frequency Features (2–9 occurrences)

Mostly noise, but some may be real features worth keeping.

| Count | Feature | Keep? |
|-------|---------|-------|
| 9 | `BASKET` | |
| 9 | `BE` | |
| 9 | `BISEL-PANEL` | |
| 9 | `EFIN-COIL` | |
| 9 | `FAN` | |
| 9 | `FANS` | |
| 9 | `FRICK` | |
| 9 | `FULLSEAM-6` | |
| 9 | `NO ELECTRICAL` | |
| 9 | `PAINTED-TEX-AL` | |
| 9 | `PERF` | |
| 9 | `PIPE` | |
| 9 | `VE` | |
| 9 | `WT-LDV` | |
| 8 | `316LSS` | |
| 8 | `AL` | |
| 8 | `CONTROLS` | |
| 8 | `CS-COIL` | |
| 8 | `CS-COILS` | |
| 8 | `EBTRON` | |
| 8 | `EMB` | |
| 8 | `FROM` | |
| 8 | `FULL-SEAM` | |
| 8 | `FULLSEAM-4` | |
| 8 | `GREENHECK` | |
| 8 | `PART-TIER` | |
| 8 | `PREPAINT` | |
| 8 | `SKID` | |
| 8 | `TEST-LAV` | |
| 8 | `VWT-LD` | |
| 8 | `WHL` | |
| 7 | `10'4"X11X35` | |
| 7 | `COLOR` | |
| 7 | `CS-BISEL` | |
| 7 | `FS-VFD` | |
| 7 | `GALV` | |
| 7 | `HEAT` | |
| 7 | `INSTALL` | |
| 7 | `LD` | |
| 7 | `LEAK&DEFLECTION` | |
| 7 | `LEAK&DEFLECTION TEST` | |
| 7 | `SQ-TUNNEL` | |
| 7 | `VESTIBULE` | |
| 7 | `VF` | |
| 7 | `WT` | |
| 7 | `WT-LDAV` | |
| 6 | `AT` | |
| 6 | `C-C` | |
| 6 | `CO` | |
| 6 | `CONST` | |
| 6 | `CURB` | |
| 6 | `DEFLECTION` | |
| 6 | `EPOXY` | |
| 6 | `ETL-CERT` | |
| 6 | `FLOOR` | |
| 6 | `IN` | |
| 6 | `PARTIAL-TIER` | |
| 6 | `REC` | |
| 6 | `SIZE` | |
| 6 | `STACKS-W` | |
| 6 | `TIERED` | |
| 6 | `WT-L-D` | |
| 5 | `10'4"X14X29` | |
| 5 | `16GA` | |
| 5 | `316-DRAINPAN` | |
| 5 | `AIR` | |
| 5 | `CANADA` | |
| 5 | `COI` | |
| 5 | `CS-GREENHECK` | |
| 5 | `FLOORS` | |
| 5 | `GUTNER-COIL` | |
| 5 | `LA` | |
| 5 | `MED` | |
| 5 | `MOD-UTB` | |
| 5 | `PENETRATION` | |
| 5 | `SECTION` | |
| 5 | `SIDEXSIDE` | |
| 5 | `SOUND-TEST` | |
| 5 | `SP` | |
| 5 | `STYLE` | |
| 5 | `TEST-L-D` | |
| 5 | `WRAPPER` | |
| 5 | `WT-D` | |
| 4 | `316L-COMPONENTS` | |
| 4 | `316L-DP` | |
| 4 | `ALL` | |
| 4 | `C-COIL` | |
| 4 | `CEILING` | |
| 4 | `CHANGED` | |
| 4 | `CHASE` | |
| 4 | `DFT` | |
| 4 | `DFT-ENAMEL` | |
| 4 | `E-F` | |
| 4 | `E-FIN-COIL-W` | |
| 4 | `ECOATED` | |
| 4 | `EWHL` | |
| 4 | `FULLS` | |
| 4 | `FULLSEAM-8` | |
| 4 | `HU` | |
| 4 | `PCH` | |
| 4 | `PCHA` | |
| 4 | `PLATE TO PLATE HX` | |
| 4 | `SECTIONS` | |
| 4 | `SEGMENTS` | |
| 4 | `SIDEXSIDE-W` | |
| 4 | `SOME` | |
| 4 | `STACK` | |
| 4 | `SUSPENDED` | |
| 4 | `TP` | |
| 4 | `UTL` | |
| 4 | `WET` | |
| 4 | `WT-LA` | |
| 4 | `X6X15CS-HEATINGCOIL` | |
| 4 | `XA` | |
| 3 | `**PENALTY` | |
| 3 | `10'4"X17X26` | |
| 3 | `316-COMP` | |
| 3 | `316SS-CO` | |
| 3 | `AND` | |
| 3 | `BAE` | |
| 3 | `BISE` | |
| 3 | `BURNER` | |
| 3 | `CHANNELS` | |
| 3 | `COMPLE` | |
| 3 | `COND` | |
| 3 | `CS-TAMCO-EBTRON` | |
| 3 | `CU-FIN` | |
| 3 | `DRC-DISC` | |
| 3 | `E-FI` | |
| 3 | `EP-W` | |
| 3 | `EPLFN` | |
| 3 | `FIBERGLASS-INSULATION` | |
| 3 | `FLT` | |
| 3 | `FOR` | |
| 3 | `FS-HW` | |
| 3 | `FU` | |
| 3 | `HEAT-PIPE` | |
| 3 | `HEPA` | |
| 3 | `JOB-MUST` | |
| 3 | `L-D-V` | |
| 3 | `LDAMAGES` | |
| 3 | `MUNTERS` | |
| 3 | `NG-HUM` | |
| 3 | `NOTE-PIPE-HRS` | |
| 3 | `ONLY` | |
| 3 | `PANEL` | |
| 3 | `PAPST` | |
| 3 | `PIPING` | |
| 3 | `REQUIRES` | |
| 3 | `SELNAV` | |
| 3 | `SIDE-BY-SIDE` | |
| 3 | `SPECIAL` | |
| 3 | `SS-DIAM-PLATE` | |
| 3 | `SWRA` | |
| 3 | `VES` | |
| 3 | `VWT-LDS` | |
| 3 | `WELDED` | |
| 3 | `WIND` | |
| 3 | `WING-CO` | |
| 3 | `WITNES` | |
| 3 | `X74X` | |
| 3 | `ZA` | |
| 3 | `ZA-FANS` | |
| 2 | `0)2` | |
| 2 | `10'3"X11X36` | |
| 2 | `10'3"X7X11` | |
| 2 | `10'4"X11X27` | |
| 2 | `10'6"X16X22` | |
| 2 | `10.5X20X34` | |
| 2 | `2X` | |
| 2 | `316LSS-DRAINPAN` | |
| 2 | `316SS` | |
| 2 | `338LX135WX134H` | |
| 2 | `ACE` | |
| 2 | `ACU` | |
| 2 | `AIR-X` | |
| 2 | `AJ` | |
| 2 | `AL-B` | |
| 2 | `ALBASE` | |
| 2 | `APPROVED` | |
| 2 | `ARE` | |
| 2 | `BASE-16G90-16SS` | |
| 2 | `BEING` | |
| 2 | `BOLT` | |
| 2 | `BUILT` | |
| 2 | `BY` | |
| 2 | `CAULK` | |
| 2 | `COIL-HERE` | |
| 2 | `CONNECT-W` | |
| 2 | `CONSTRUCT` | |
| 2 | `CONSTRUCTION` | |
| 2 | `CONTROL` | |
| 2 | `COOK` | |
| 2 | `COOLER` | |
| 2 | `CS-HUM(FIELD` | |
| 2 | `CS-HW` | |
| 2 | `CS-VR` | |
| 2 | `DECK` | |
| 2 | `DFT-EPOX` | |
| 2 | `DOOR` | |
| 2 | `DRC-SPPP` | |
| 2 | `DU` | |
| 2 | `DUAL-TUNNEL` | |
| 2 | `E-FIN-COI` | |
| 2 | `E-FIN-COIL-WITH` | |
| 2 | `ELECTRO` | |
| 2 | `ENAMEL` | |
| 2 | `ENERGY` | |
| 2 | `ENG` | |
| 2 | `ERI-CORE` | |
| 2 | `ERWHL` | |
| 2 | `EVAP` | |
| 2 | `FMED` | |
| 2 | `FRAME` | |
| 2 | `FULLSEAM-1` | |
| 2 | `FULLSEAM-5` | |
| 2 | `G-HECK` | |
| 2 | `GENESIS-SP` | |
| 2 | `GRATING` | |
| 2 | `HERSITE` | |
| 2 | `HR` | |
| 2 | `HW-W` | |
| 2 | `HX-WITH-EPOXY-COAT` | |
| 2 | `INFRARED` | |
| 2 | `JADEC` | |
| 2 | `KNOCKDOWN` | |
| 2 | `LOOSELY` | |
| 2 | `MEDIUM*` | |
| 2 | `MEDIUM-MILLER` | |
| 2 | `MMP-BOTTOM` | |
| 2 | `MMP-CS-EBTRON` | |
| 2 | `MMP-MOVE` | |
| 2 | `MMP-TOP` | |
| 2 | `MONITORING` | |
| 2 | `NO-ELECTRICAL` | |
| 2 | `NOAA` | |
| 2 | `O(4` | |
| 2 | `OUTSIDE` | |
| 2 | `PARTIAL-KDOWN` | |
| 2 | `PIP` | |
| 2 | `POLY` | |
| 2 | `RETURN` | |
| 2 | `SECTION-KDOWN` | |
| 2 | `SEIS-CONST` | |
| 2 | `SHRIN` | |
| 2 | `SILICONE` | |
| 2 | `SO` | |
| 2 | `SPEC` | |
| 2 | `SPPP(CS)` | |
| 2 | `SS-CONDUIT` | |
| 2 | `SS-TP` | |
| 2 | `STAG` | |
| 2 | `STATION` | |
| 2 | `SUPPLY` | |
| 2 | `SWR` | |
| 2 | `TEST-L-D-A` | |
| 2 | `TEST-LDAV` | |
| 2 | `TEST-SOUND` | |
| 2 | `THESE` | |
| 2 | `TIG-FLOOR` | |
| 2 | `TIG-WELD` | |
| 2 | `TRANSFERRED` | |
| 2 | `UNITS` | |
| 2 | `VERTICAL` | |
| 2 | `VEST-WHITE` | |
| 2 | `VFD(CS)` | |
| 2 | `VFD-FANS` | |
| 2 | `VWT-LDA` | |
| 2 | `WALL&CE` | |
| 2 | `WILL` | |
| 2 | `WITH` | |
| 2 | `WLD` | |
| 2 | `WT-LAV` | |

---

## Single-Occurrence Features (1 each)

Almost entirely noise. Scan for any real features worth keeping.

`#1`, `#2`, `#3`, `#4`, `#5`, `#6`, `#7`, `#8`, `#9`, `#10`, `#11`, `(2"`, `(BOTTOM)`, `(QTY`, `(TOP)`, `**`, `**NO`, `*ENAMEL`, `*LEAK&DEFLECTION`, `*NO`, `0)3`, `1)2`, `10'1"X8X29`, `10'1"X9X10`, `10'2"X13X30`, `10'3"X11X11`, `10'3"X13X52`, `10'3"X16X30`, `10'3"X17X25`, `10'3X16X28`, `10'4"X8X19`, `10'4X14X29`, `10'5"X11X34`, `10'6"X10X24`, `10'6"X12X36`, `10'6"X14X22`, `10'6"X14X41`, `10'6"X15X20`, `10'6"X15X27`, `10'6"X9X21`, `10.5X11X34`, `10.5X20X35`, `16"-ALDP`, `20016.`, `3-TUNNEL`, `3-TUNNELS`, `30K`, `316-COMPONENTS`, `316L-CO`, `316L-COM`, `316L-COMPONENT`, `316L-DRAINPAN`, `316SS-C`, `380LX126WX116H`, `63X`, `9.5X14X34`, `ACOUSTIFLO`, `ACU-TEST`, `ACUAIR`, `AEROF`, `AEROFIN-COILS`, `AIRX-HW`, `AL-BA`, `AL-BAS`, `AL-WALL`, `ALEM`, `ANGLED`, `AREOFIN`, `AREOVENT`, `BEPL`, `BIG`, `BILL`, `BOT`, `BOTT`, `BOTTOM-COILS`, `BSEL-SPPP`, `BULKHEADS`, `CA`, `CENTER-SPL`, `CERENHANCED`, `CIP`, `COA`, `COLOR-PURE`, `COM`, `COMEFRI`, `COMPLICATED`, `CONDU`, `CONNECT`, `CONNECTS-TO-18674`, `CONST.`, `CONT`, `CORNER`, `COS`, `CS-CONTROLS-CANAD`, `CS-CONTROLS-CANADA`, `CS-EBM`, `CS-EH`, `CS-EMB`, `CS-EMERGENT`, `CS-H`, `CS-HW(FIELD`, `CS-HX`, `CS-VRF-K`, `CU-F`, `CU-FIN-CO`, `CU-FIN-COIL-WITH-E`, `CU-V`, `D-CAMFIL`, `D-COIL`, `DAMAGE`, `DEFENSE-PRIOROTY`, `DEFL`, `DEHUMIDIFIER`, `DESICANT`, `DF`, `DFT-EP`, `DOD-PRIORITY`, `DORAL`, `DRC-DISCONNECT`, `DRC-MMP`, `DRC-S`, `DTM-SC`, `E-FIN(W`, `E-FIN-CO`, `E-FIN-COIL-UV-TOP`, `E-FIN-COILS`, `EB`, `EFIN`, `EFIN-COIL-W`, `EH`, `EL`, `ELE`, `ELECTICAL`, `ENG-UNIT`, `EP-UV`, `EPFN`, `EPOX-WHITE`, `EPQN`, `ERI-CERTIFIC`, `EVERYTHING`, `EVERYTHING SS`, `EXCHANGER`, `EXT`, `FA`, `FACTORY-PROVIDE`, `FAST`, `FASTN`, `FIELD`, `FIL`, `FLOOD`, `FLOOD-TEST`, `FLOOR-WT-LDV`, `FLOW-MILLER`, `FRAMES`, `FS-COILS`, `FULL`, `FULL SEAM`, `FULLSEAM-10`, `FULLSEAM-2`, `GALV)2`, `GAS`, `GENESIS-KDOWN`, `GENESIS-SC-MMP`, `GH-FANS`, `GO`, `GOIN`, `GUNTNER`, `HEATCO-BURNER`, `HERESITE-C`, `HERESITE-PHENOLIC-COILS`, `HIGH-TEMP-CAULK`, `HIM`, `HSB-SS`, `HSG`, `HX(CS)`, `HYDRONIC`, `ING`, `INT`, `INTENSITY`, `INTER`, `INTERNAL`, `INTERNALS`, `IS`, `KINSLEY`, `KONVEKTA`, `L&D-WITNESS`, `L-T`, `LAUE-FIN-COIL`, `LDA`, `LDS`, `LDV`, `LEAK&DE`, `LEAK&DEFL`, `LEAK&DEFLE`, `LEAKAGE`, `LIQ`, `MCDOWEL`, `MEDIUM*SEISMIC`, `MEDIUM-LEAK`, `MERGING`, `MIDDLE-SPLIT`, `MISTOP`, `MMPHUM`, `MOD-TB-BASE`, `MODIFIED-UTB`, `MOTOR`, `MUNTER`, `MZ20290`, `MZ43360`, `NIH`, `NO-FLOOR-PEN`, `ORDER`, `OSP`, `PA`, `PAINT-CHAMPAGNE`, `PAINT-DELETED`, `PAINT-NETSUKE`, `PAINT?`, `PARTIAL`, `PARTIAL-KDOWN-TIER`, `PE`, `PER`, `PH`, `PHENOLIC`, `PI`, `PICKING-AIRFLOW`, `PIECE`, `PLENUM`, `PLUG`, `PPFULLSEAM-6`, `PR`, `PREPAI`, `PREPAIN`, `PRO`, `PROPANE`, `PROTOTYPE`, `PROVIDED`, `PROVIDED)`, `PRT-KDOWN`, `PSU`, `PUMP`, `RAILS`, `REGEN`, `REPLACEMENT`, `REQ'D`, `S-ELECTROFIN`, `S-WRAP`, `SAMPLE`, `SC`, `SCOLOR`, `SEC`, `SECTION-NGH`, `SEIS CERT`, `SEIS-C`, `SEIS-CONSTRUCTION`, `SEMI-HIGH-PIPE`, `SHIP`, `SHIPPING`, `SHRINK`, `SHRINKWRAP`, `SIDEXSIDE-TU`, `SILICO`, `SLICONE-FREE`, `SPLIT-TIER`, `SQ'S`, `SQ-GENESES`, `SQ-GENESIS`, `SS-DIA`, `SS-DIA-PLATE`, `SS-DIAM`, `SS-DIAMOND-PLATE`, `STACK-19647` through `STACK-19809`, `STACK-W-18672`, `STACK-W-18673`, `STACK-WITH-18630`, `STACKS-18722` through `STACKS-18737`, `STACKS-WITH-18631`, `STD`, `STI`, `SUB`, `SUBFL-2`, `SUPPLIED)`, `SW`, `T-SHAPE`, `TA`, `TAMCO-DAMPER`, `TAMCO-EBRTON`, `TCF(CS)`, `TCF(FIELD`, `TEXAL`, `TEXT-AL`, `TIG-WE`, `TIG-WELD-FLOOR`, `TOPCOA`, `TOPCOAT`, `TOUGH`, `TUNNE`, `UM`, `UNIT-FULLSEAM`, `UNIT-PROTOTYPE-SHIPS`, `UNITS)`, `UTB-WALLS`, `UV)`, `V-WT`, `VEST-STITCH`, `VFD(SHIPLOOSE)`, `VFD-WITH-MMP`, `VFP`, `VIFB-COIL`, `WALL)`, `WHEEL`, `WHITE`, `WHITE**D`, `WING-COI`, `WIT`, `WITN`, `WO`, `WRAP`, `WT-ADLV`, `WT-L-D-SOUND`, `WT-LD FLOOD TEST`, `WT-LDS`, `X10X28`, `X12X24`, `X14X20`, `YV`

---

## Sample Parses (first 25 units)

For sanity-checking the parser output.

| COM # | Description | Type | Dimensions | Features | Flags |
|-------|-------------|------|------------|----------|-------|
| 252994 | `152X156X92 PROTOTYPE SELNAV` | — | `152X156X92` | `PROTOTYPE`, `SELNAV` | — |
| 14212 | `I)2 10'5"X11X34 HW/HUM` | `I)2` | `10'5"X11X34` | `10'5"X11X34`, `HW`, `HUM` | — |
| 14181 | `O)3 10X34X40 WT-L-D/VEST/MMP/VFD` | `O)3` | `10X34X40` | `WT-L-D`, `VEST`, `MMP`, `VFD` | — |
| 14230 | `I)2 7X10X13  HEAT PIPE/MMP` | `I)2` | `7X10X13` | `HEAT`, `PIPE`, `MMP` | — |
| 14247 | `O)2 4x5x22 LAU, ABB` | `O)2` | `4X5X22` | `LAU`, `ABB` | — |
| 14201 | `I)2 6X7X18 WT-L/CAMFIL/CU FIN COIL` | `I)2` | `6X7X18` | `WT-L`, `CAMFIL`, `CU`, `FIN`, `COIL` | — |
| 14203 | `I)3 6X7X22 WT L/D-CAMFIL/CU FIN COIL` | `I)3` | `6X7X22` | `WT`, `D-CAMFIL`, `CU`, `FIN`, `COIL` | — |
| 14207 | `I)3 6X7X21 WT L-D/CAMFIL/CU FIN COIL` | `I)3` | `6X7X21` | `WT`, `L-D`, `CAMFIL`, `CU`, `FIN`, `COIL` | — |
| 14208 | `I)3 7X9X19 WT L-D/CAMFIL/CU FIN COIL` | `I)3` | `7X9X19` | `WT`, `L-D`, `CAMFIL`, `CU`, `FIN`, `COIL` | — |
| 14209 | `I)3 7X9X20 WT L-D/CAMFIL/CU FIN COIL` | `I)3` | `7X9X20` | `WT`, `L-D`, `CAMFIL`, `CU`, `FIN`, `COIL` | — |
| 14202 | `I)2 9X9X20 WT L-D/CAMFIL/CU FIN COIL` | `I)2` | `9X9X20` | `WT`, `L-D`, `CAMFIL`, `CU`, `FIN`, `COIL` | — |
| 252482 | `134x142x264 large` | — | `134X142X264` | `LARGE` | — |
| 252483 | `134x142x264 Large` | — | `134X142X264` | `LARGE` | — |
| 252480 | `134x142x264 Large` | — | `134X142X264` | `LARGE` | — |
| 252481 | `134x142x264 large` | — | `134X142X264` | `LARGE` | — |
| 14206 | `I)3 8X7X32 WT L-D/CAMFIL/CU FIN COIL` | `I)3` | `8X7X32` | `WT`, `L-D`, `CAMFIL`, `CU`, `FIN`, `COIL` | — |
| 14197 | `O)2 10X16X22 SEISMIC/ENERGY WHL/DUAL TUNNEL` | `O)2` | `10X16X22` | `SEISMIC`, `ENERGY`, `WHL`, `DUAL`, `TUNNEL` | — |
| 14196 | `O)2 10X16X25 SEISMIC/ENERGY WHL/DUAL TUNNEL` | `O)2` | `10X16X22` | `SEISMIC`, `ENERGY`, `WHL`, `DUAL`, `TUNNEL` | — |
| 14213 | `I)2 10.5X11X34 HW/HUM` | `I)2` | `10.5X11X34` | `10.5X11X34`, `HW`, `HUM` | — |
| 14177 | `O)3 11X38X43 WT-L-D/ELEC HTR/VEST/UV/VFD` | `O)3` | `11X38X43` | `WT-L-D`, `ELEC`, `HTR`, `VEST`, `UV`, `VFD` | — |
| 252747 | `66X84X222 FLOW *MUST USE GENESIS PAINT*` | — | `66X84X222` | `FLOW` | `MUST USE GENESIS PAINT` |
| 14232 | `I)3 8X12X15 KDOWN/TIER/MMP` | `I)3` | `8X12X15` | `KDOWN`, `TIER`, `MMP` | — |
| 14154 | `I)2 4X3X13 KDOWN/EP/SA/EBM PAPST` | `I)2` | `4X3X13` | `KDOWN`, `EP`, `SA`, `EBM`, `PAPST` | — |
| 252745 | `76X102X227 FLOW *MUST USE GENESIS PAINT*` | — | `76X102X227` | `FLOW` | `MUST USE GENESIS PAINT` |

---

## Known Parser Issues

1. **Dimension fragments leak as features** — Tokens like `10'5"X11X34` and `10.5X11X34` appear as features even though they're dimensions. The dimension regex extracts them correctly but they also survive into the feature tokenizer.

2. **Slash/dash splitting creates noise** — `WT-L-D` is real, but `D-CAMFIL`, `L-D`, `LEAK&DEFLECTION` are artifacts of splitting on `/` and `-`.

3. **No normalization** — `AL-BASE` and `AL BASE` and `ALBASE` are counted separately. Same with `K-DOWN`/`KDOWN`, `FULLSEAM`/`FULL-SEAM`/`FULL SEAM`, `E-FIN`/`EFIN`, etc.

4. **Flags in asterisks are extracted correctly** — `*PRE-PAINT*`, `*MUST USE GENESIS PAINT*` etc. work fine.

5. **Compound features** — `FLOOD TEST`, `FULL SEAM`, `PLATE TO PLATE HX` are handled by the `_COMPOUND_FEATURES` set, but variants like `FLOOD-TEST` or `FULL-SEAM` are not caught.
