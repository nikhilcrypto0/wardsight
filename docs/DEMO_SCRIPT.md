# WardSight: 3-minute demo video

Record with QuickTime (File > New Screen Recording) or OBS at 1440p. Browser at 100% zoom, one
window, notifications off. Start from a clean state: Audit log > Reset demo.

Before recording:

```
uv run wardsight-api                    # terminal 1
cd web && npm run dev                   # terminal 2, then open http://localhost:3000
```

| Time | Screen | Do | Say (plain, your own words) |
| --- | --- | --- | --- |
| 0:00 | Ward replay, paused at Day 1 | Nothing yet | "Hospitals get paid, and get audited, on what the doctor writes, not on what the labs show. When the two disagree, nobody notices until after the patient goes home. I built WardSight to catch it while the patient is still in the bed." |
| 0:15 | Ward replay | Press Play at 10x | "This is a synthetic hospital: 200 patients over two weeks. Every six hours the engine re-reads each chart. Amber is a gap, purple means a query is with the physician, green is resolved." |
| 0:45 | Ward replay | Pause around Day 9, point at the live feed | "Here: oxygen 87% on room air at hour 0, but respiratory failure never written. Caught at hour zero, not after discharge." |
| 1:00 | CDI worklist | Click D0011 | "Each row is a gap with the billing category now and if resolved." |
| 1:10 | Chart D0011 | Point at the evidence list | "Plain code decides. Blood pressure 63, platelets 121, bilirubin 1.6, cultures and antibiotics. That meets Sepsis-3, and the notes say only urinary tract infection." |
| 1:25 | Query card | Type "Please document sepsis, it raises the DRG" at the end | "The AI only drafts the question. A rules check from the official ACDIS/AHIMA guidelines watches every word. Leading wording, money talk, naming the diagnosis: blocked, and Approve locks." |
| 1:45 | Query card | Reload, click Approve and send | "The real query never names sepsis. The physician picks from fixed options, including 'unable to determine'." |
| 1:55 | Physician inbox | Click "Let the simulated physician reply" | "A simulated physician answers. The answer becomes an addendum, the chart is rescanned." |
| 2:05 | Chart D0011 | Scroll to the billing card | "Resolved. Billing category 690 to 872. The record is now accurate." |
| 2:15 | Ward replay, end | Point at "Billing categories corrected" and an "unsupported" feed line | "It also works the other way: diagnoses written without evidence get ruled out, and the bill goes down. This is about accuracy, not padding." |
| 2:30 | Audit log | Scroll | "Every decision is logged and the log is append-only. Nothing reaches a physician without a human click." |
| 2:40 | README on GitHub | Scroll to the test table | "Synthetic data only. 300 charts with planted mistakes and an answer key, 100 held out. Python, FHIR, DuckDB to Snowflake, React. Link below." |
| 2:55 | End | | "Thanks for watching." |

Keep it under 3:00. Re-record any segment rather than cutting mid-sentence.

## Facts to keep straight on camera

- All data is synthetic (Synthea patients plus a scenario engine). No real patients.
- Dev-set detection score (75/75, 0 false alarms) uses template notes, the easy case. Do not quote it as
  clinical accuracy. The held-out set is scored once, at the end.
- The physician is simulated (rule-based). Say "simulated physician".
