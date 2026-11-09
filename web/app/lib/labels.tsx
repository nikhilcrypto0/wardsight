import type { Kind, Status } from "./api";

export const CONDITION: Record<string, string> = {
  aki: "Acute kidney injury",
  sepsis: "Sepsis",
  hyponatremia: "Hyponatremia",
  abla: "Acute blood loss anemia",
  arf: "Acute hypoxic respiratory failure",
  hf: "Acute systolic heart failure",
};

export const KIND: Record<Kind, string> = {
  missing_dx: "Missing diagnosis",
  unsupported_dx: "Not supported by evidence",
};

const STATUS_STYLE: Record<Status, [string, string]> = {
  pending_review: ["Needs review", "bg-blue-50 text-blue-700 ring-blue-200"],
  needs_rewrite: ["Needs rewrite", "bg-orange-50 text-orange-700 ring-orange-200"],
  rejected: ["Rejected", "bg-slate-100 text-slate-600 ring-slate-200"],
  sent: ["Sent to physician", "bg-violet-50 text-violet-700 ring-violet-200"],
  answered: ["Answered, still open", "bg-amber-50 text-amber-800 ring-amber-200"],
  resolved: ["Resolved", "bg-emerald-50 text-emerald-700 ring-emerald-200"],
};

export function StatusBadge({ status }: { status: Status }) {
  const [label, style] = STATUS_STYLE[status];
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ${style}`}>
      {label}
    </span>
  );
}

export function KindBadge({ kind }: { kind: Kind }) {
  const style = kind === "missing_dx" ? "text-sky-700 bg-sky-50" : "text-rose-700 bg-rose-50";
  return <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${style}`}>{KIND[kind]}</span>;
}

export const SERIES_LABEL: Record<string, [string, string]> = {
  creatinine: ["Creatinine", "mg/dL"],
  sodium: ["Sodium", "mmol/L"],
  hemoglobin: ["Hemoglobin", "g/dL"],
  platelets: ["Platelets", "K/uL"],
  wbc: ["White cells", "K/uL"],
  map: ["Mean arterial pressure", "mmHg"],
  spo2: ["SpO2", "%"],
  resp_rate: ["Respiratory rate", "/min"],
  heart_rate: ["Heart rate", "/min"],
  temp: ["Temperature", "°C"],
  o2_flow: ["Oxygen flow", "L/min"],
  bnp: ["BNP", "pg/mL"],
  lvef: ["LVEF", "%"],
  lactate: ["Lactate", "mmol/L"],
  bilirubin: ["Bilirubin", "mg/dL"],
  pao2: ["PaO2", "mmHg"],
};

export function DrgShift({ from, to, size = "sm" }: { from: number | null; to: number | null; size?: "sm" | "lg" }) {
  if (from == null || to == null) return <span className="text-slate-400">—</span>;
  const changed = from !== to;
  const text = size === "lg" ? "text-lg" : "text-sm";
  return (
    <span className={`font-mono ${text} ${changed ? "text-slate-900" : "text-slate-400"}`}>
      {from} <span className="text-slate-400">→</span> {to}
    </span>
  );
}
