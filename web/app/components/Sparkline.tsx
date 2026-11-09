import { SERIES_LABEL } from "../lib/labels";

const W = 220;
const H = 44;

// Smallest vertical range drawn per measurement. Without it, normal noise
// (SpO2 96-97%, creatinine 0.72-0.77) is stretched to fill the box and reads as
// instability. With it, only clinically meaningful change looks like change.
const MIN_SPAN: Record<string, number> = {
  creatinine: 1.0, sodium: 10, hemoglobin: 3, platelets: 100, wbc: 8, map: 30, spo2: 10,
  resp_rate: 12, heart_rate: 40, temp: 2, o2_flow: 6,
};

interface SparklineProps {
  name: string;
  points: [number, number][];
}

/** Trend of one measurement over the stay; low and high values are labeled. */
export default function Sparkline({ name, points }: SparklineProps) {
  const [label, unit] = SERIES_LABEL[name] ?? [name, ""];
  const values = points.map((p) => p[1]);
  const lo = Math.min(...values);
  const hi = Math.max(...values);
  const tMax = Math.max(...points.map((p) => p[0]), 1);
  const span = Math.max(hi - lo, MIN_SPAN[name] ?? 0, 1e-9);
  const floor = (lo + hi) / 2 - span / 2;
  const x = (t: number) => (t / tMax) * (W - 4) + 2;
  const y = (v: number) => H - 4 - ((v - floor) / span) * (H - 8);
  const path = points.map((p, i) => `${i ? "L" : "M"}${x(p[0]).toFixed(1)} ${y(p[1]).toFixed(1)}`).join(" ");
  const last = values[values.length - 1];

  return (
    <div className="rounded-lg ring-1 ring-slate-200 bg-white p-3">
      <div className="flex items-baseline justify-between">
        <span className="text-xs font-medium text-slate-600">{label}</span>
        <span className="font-mono text-sm text-slate-900">
          {last}
          <span className="ml-1 text-xs text-slate-400">{unit}</span>
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="mt-1 w-full h-11" role="img" aria-label={`${label} trend`}>
        <path d={path} fill="none" stroke="#0f766e" strokeWidth="1.5" />
      </svg>
      <div className="flex justify-between font-mono text-[11px] text-slate-400">
        <span>low {lo}</span>
        <span>high {hi}</span>
      </div>
    </div>
  );
}
