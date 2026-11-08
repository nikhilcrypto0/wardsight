"""Evidence rules: does the chart meet published criteria for each condition?

Plain code, no AI. Each rule returns the indicators it used (value + hour) so
a reviewer can see exactly why it fired. Thresholds come from `criteria.py`;
the logic here is written independently of the data-factory generator.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from wardsight import criteria as c
from wardsight.engine.chart import Chart

ANTIBIOTICS = ("ceftriaxone", "piperacillin", "cefazolin", "cefepime", "vancomycin", "meropenem")
HYPONATREMIA_TREATMENT = ("fluid restriction", "sodium chloride 1 g", "tolvaptan", "hypertonic saline")
BLEEDING = re.compile(r"\b(bleeding|hemorrhage|melena|hematemesis)\b")
TRANSFUSION = re.compile(r"transfus|packed red blood cells")
IV_LOOP_DIURETIC = re.compile(r"\b(furosemide|bumetanide|torsemide)\b.*\biv\b", re.IGNORECASE)
SERIAL_DRAWS_48H = 4  # sodium checked at least this often in 48 h = active monitoring
ARF_MIN_INDICATORS = 2


@dataclass(frozen=True)
class Indicator:
    t_hours: float
    text: str


@dataclass(frozen=True)
class Evidence:
    condition: str
    met: bool
    indicators: tuple[Indicator, ...] = ()

    def summary(self) -> str:
        return "; ".join(f"h{i.t_hours:g}: {i.text}" for i in self.indicators)


def _no(condition: str) -> Evidence:
    return Evidence(condition, False)


def aki(chart: Chart) -> Evidence:
    """KDIGO: creatinine +0.3 mg/dL within 48 h, or 1.5x within 7 days."""
    cr = chart.series("creatinine")
    for i, (t0, v0) in enumerate(cr):
        for t1, v1 in cr[i + 1:]:
            within_48 = t1 - t0 <= c.AKI_ABS_WINDOW_H and v1 - v0 >= c.AKI_ABS_RISE_MG_DL
            within_7d = t1 - t0 <= 7 * 24 and v1 >= c.AKI_REL_RISE * v0
            if within_48 or within_7d:
                return Evidence("aki", True, (Indicator(t0, f"creatinine {v0:g} mg/dL"),
                                              Indicator(t1, f"creatinine {v1:g} mg/dL")))
    return _no("aki")


def _sofa_renal(cr: float) -> int:
    return 0 if cr < 1.2 else 1 if cr < 2.0 else 2 if cr < 3.5 else 3 if cr < 5.0 else 4


def _sofa_coag(plt: float) -> int:
    return 0 if plt >= c.SOFA_PLATELETS_K else 1 if plt >= 100 else 2 if plt >= 50 else 3 if plt >= 20 else 4


def _sofa_liver(bili: float) -> int:
    return 0 if bili < c.SOFA_BILIRUBIN_MG_DL else 1 if bili < 2.0 else 2 if bili < 6.0 else 3


def sepsis(chart: Chart) -> Evidence:
    """Sepsis-3: suspected infection (cultures + antibiotics) and SOFA rise >= 2."""
    texts = [(t, s.lower()) for t, s in chart.texts()]
    cultures = [t for t, s in texts if "blood culture" in s]
    antibiotics = [t for t, s in texts if any(a in s for a in ANTIBIOTICS)]
    if not cultures or not antibiotics:
        return _no("sepsis")
    found: list[Indicator] = [Indicator(cultures[0], "blood cultures drawn"),
                              Indicator(antibiotics[0], "antibiotics started")]
    points = 0
    maps = chart.series("map")
    if maps and min(v for _, v in maps) < c.SOFA_MAP_MMHG:
        t, v = min(maps, key=lambda p: p[1])
        points += 1
        found.append(Indicator(t, f"MAP {v:g} mmHg"))
    for key, scorer, unit in (("platelets", _sofa_coag, "K/uL"), ("bilirubin", _sofa_liver, "mg/dL")):
        values = chart.series(key)
        if values:
            worst = min(values, key=lambda p: p[1]) if key == "platelets" else max(values, key=lambda p: p[1])
            if scorer(worst[1]):
                points += scorer(worst[1])
                found.append(Indicator(worst[0], f"{key} {worst[1]:g} {unit}"))
    cr = chart.series("creatinine")
    if cr:  # renal points count only as a rise from the patient's own lowest value
        renal = _sofa_renal(max(v for _, v in cr)) - _sofa_renal(min(v for _, v in cr))
        if renal > 0:
            points += renal
            t, v = max(cr, key=lambda p: p[1])
            found.append(Indicator(t, f"creatinine {v:g} mg/dL"))
    met = points >= c.SEPSIS_SOFA_DELTA
    return Evidence("sepsis", met, tuple(found) if met else ())


def hyponatremia(chart: Chart) -> Evidence:
    """Na < 135 that was clinically significant: treated or actively monitored."""
    na = chart.series("sodium")
    low = [(t, v) for t, v in na if v < c.HYPONATREMIA_NA_MMOL_L]
    if not low:
        return _no("hyponatremia")
    treated = [(t, s) for t, s in chart.texts() if any(k in s.lower() for k in HYPONATREMIA_TREATMENT)]
    draws_48h = sum(1 for t, _ in na if t <= 48)
    if not treated and draws_48h < SERIAL_DRAWS_48H:
        return _no("hyponatremia")
    t, v = min(low, key=lambda p: p[1])
    found = [Indicator(t, f"sodium {v:g} mmol/L")]
    found += [Indicator(tt, s) for tt, s in treated[:1]]
    if draws_48h >= SERIAL_DRAWS_48H:
        found.append(Indicator(48, f"sodium checked {draws_48h} times in 48 h"))
    return Evidence("hyponatremia", True, tuple(found))


def abla(chart: Chart) -> Evidence:
    """Hemoglobin drop >= 2 g/dL with a bleeding source or a transfusion."""
    hgb = chart.series("hemoglobin")
    best = None
    for i, (t0, v0) in enumerate(hgb):
        for t1, v1 in hgb[i + 1:]:
            if v0 - v1 >= c.ABLA_HGB_DROP_G_DL and (best is None or v0 - v1 > best[0]):
                best = (v0 - v1, t0, v0, t1, v1)
    if best is None:
        return _no("abla")
    support = [(t, s) for t, s in chart.texts() if BLEEDING.search(s.lower()) or TRANSFUSION.search(s.lower())]
    if not support:
        return _no("abla")
    _, t0, v0, t1, v1 = best
    return Evidence("abla", True, (Indicator(t0, f"hemoglobin {v0:g} g/dL"),
                                   Indicator(t1, f"hemoglobin {v1:g} g/dL"),
                                   *(Indicator(t, s) for t, s in support[:2])))


def arf(chart: Chart) -> Evidence:
    """Acute hypoxic respiratory failure: >= 2 indicators plus oxygen therapy."""
    o2 = dict(chart.series("o2_flow"))
    found: list[Indicator] = []
    room_air = [(t, v) for t, v in chart.series("spo2") if o2.get(t, 0.0) == 0.0 and v < c.ARF_SPO2_PCT]
    if room_air:
        t, v = min(room_air, key=lambda p: p[1])
        found.append(Indicator(t, f"SpO2 {v:g}% on room air"))
    pao2 = [(t, v) for t, v in chart.series("pao2") if v < c.ARF_PAO2_MMHG]
    if pao2:
        found.append(Indicator(pao2[0][0], f"PaO2 {pao2[0][1]:g} mmHg"))
    rr = [(t, v) for t, v in chart.series("resp_rate") if v > c.ARF_RR_PER_MIN]
    if rr:
        t, v = max(rr, key=lambda p: p[1])
        found.append(Indicator(t, f"respiratory rate {v:g}/min"))
    oxygen = [(t, v) for t, v in o2.items() if v > 0]
    if len(found) < ARF_MIN_INDICATORS or not oxygen:
        return _no("arf")
    t, v = max(oxygen, key=lambda p: p[1])
    return Evidence("arf", True, (*found, Indicator(t, f"oxygen {v:g} L/min")))


def hf(chart: Chart) -> Evidence:
    """Acute systolic heart failure: LVEF <= 40%, BNP > 400 and IV loop diuretic."""
    lvef = [(t, v) for t, v in chart.series("lvef") if v <= c.HFREF_LVEF_PCT]
    bnp = [(t, v) for t, v in chart.series("bnp") if v > c.HF_BNP_PG_ML]
    diuretic = [(t, s) for t, s in chart.texts("med") if IV_LOOP_DIURETIC.search(s)]
    if not (lvef and bnp and diuretic):
        return _no("hf")
    return Evidence("hf", True, (Indicator(bnp[0][0], f"BNP {bnp[0][1]:g} pg/mL"),
                                 Indicator(lvef[0][0], f"LVEF {lvef[0][1]:g}%"),
                                 Indicator(diuretic[0][0], diuretic[0][1])))


RULES: dict[str, Callable[[Chart], Evidence]] = {
    "aki": aki, "sepsis": sepsis, "hyponatremia": hyponatremia, "abla": abla, "arf": arf, "hf": hf,
}
