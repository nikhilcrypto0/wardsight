"""MS-DRG relative weights and geometric mean length of stay (GMLOS), v44 / FY2027.

Values for the DRGs this synthetic ward produces, as published in CMS IPPS FY2027
Final Rule Table 5 (with correction notice CMS-1849-CN3), transcribed from the
per-DRG pages at quickintell.com/medical-coding/drg/<n> on 2026-11-09.
Verify against the CMS Table 5 file before any real billing or contracting use.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DrgFacts:
    weight: float  # relative weight
    gmlos: float   # geometric mean length of stay, days


DRG_FACTS: dict[int, DrgFacts] = {
    190: DrgFacts(1.0748, 3.3),  # COPD with MCC
    191: DrgFacts(0.8261, 2.6),  # COPD with CC
    192: DrgFacts(0.6288, 2.1),  # COPD without CC/MCC
    193: DrgFacts(1.2825, 3.8),  # Simple pneumonia and pleurisy with MCC
    194: DrgFacts(0.7888, 2.7),  # ... with CC
    195: DrgFacts(0.6063, 2.2),  # ... without CC/MCC
    312: DrgFacts(0.8660, 2.4),  # Syncope and collapse
    377: DrgFacts(1.8127, 4.4),  # GI hemorrhage with MCC
    378: DrgFacts(0.9732, 2.9),  # ... with CC
    379: DrgFacts(0.6381, 2.0),  # ... without CC/MCC
    602: DrgFacts(1.4273, 4.5),  # Cellulitis with MCC
    603: DrgFacts(0.8635, 3.1),  # Cellulitis without MCC
    689: DrgFacts(1.1415, 3.7),  # Kidney and urinary tract infections with MCC
    690: DrgFacts(0.8010, 2.8),  # ... without MCC
    871: DrgFacts(1.9320, 4.8),  # Septicemia or severe sepsis w/o MV >96 h with MCC
    872: DrgFacts(1.0066, 3.4),  # ... without MCC
}


def facts(drg: int) -> DrgFacts | None:
    return DRG_FACTS.get(drg)
