// Browser copy of the query rules check (src/wardsight/queries/lint.py), used by the hosted
// demo so the check runs on every keystroke without a server. tests/lint-parity.test.ts
// proves it returns exactly what the Python version returns on 2,250 cases.

export const OTHER = "Other (please specify)";
export const UNDETERMINED = "Unable to determine";

const FINANCIAL =
  /\b(drg|ms-drg|reimburse\w*|payment|paid|pay|revenue|billing|bill|money|dollars?|cost|cc|mcc|case mix|cmi|severity of illness|soi|rom|profit|financial|denials?)\b|\$/i;

const LEADING =
  /please (document|add|chart|code)|consider documenting|can you document|should be documented|supports? (a |the )?diagnosis of|meets? (the )?criteria for|consistent with|indicative of|confirm(ing)? (the |a )?diagnosis|we recommend|you should|agree that|it is likely/i;

const NUMBER = /\d+(?:\.\d+)?/g;
const MAX_STEM_CHARS = 700;
const MIN_INDICATORS: Record<string, number> = { missing_dx: 2, unsupported_dx: 1 };

export interface LintInput {
  stem: string;
  options: readonly string[];
  indicators: readonly string[];
  condition: string;
  kind: string;
  /** Diagnosis phrases for each condition, exported from the Python note reader's lexicon. */
  targets: Record<string, readonly string[]>;
}

export interface LintResult {
  ok: boolean;
  problems: string[];
}

const escapeRegex = (s: string): string => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const numbers = (s: string): string[] => s.match(NUMBER) ?? [];

export function lintQuery({ stem, options, indicators, condition, kind, targets }: LintInput): LintResult {
  const problems: string[] = [];
  const text = stem.toLowerCase();

  const financial = FINANCIAL.exec(stem);
  if (financial) problems.push(`mentions financial impact: '${financial[0]}'`);
  const leading = LEADING.exec(stem);
  if (leading) problems.push(`leading wording: '${leading[0]}'`);
  if (kind === "missing_dx") {
    for (const phrase of targets[condition] ?? []) {
      if (new RegExp(`(?<![a-z])${escapeRegex(phrase)}(?![a-z])`).test(text)) {
        problems.push(`names the diagnosis in the question: '${phrase}' (belongs only in the options)`);
        break;
      }
    }
  }

  const minimum = MIN_INDICATORS[kind];
  if (indicators.length < minimum) {
    problems.push(`cites ${indicators.length} clinical indicator(s); at least ${minimum} required`);
  }
  const allowed = new Set(indicators.flatMap(numbers));
  const invented = [...new Set(numbers(stem))].filter((n) => !allowed.has(n)).sort();
  if (invented.length) problems.push(`numbers not found in the chart indicators: ${invented.join(", ")}`);

  const lowered = new Set(options.map((o) => o.toLowerCase()));
  if (!options.includes(OTHER) || !options.includes(UNDETERMINED)) {
    problems.push("options must include 'Other (please specify)' and 'Unable to determine'");
  }
  if (kind === "missing_dx" && (lowered.has("yes") || lowered.has("no"))) {
    problems.push("yes/no options may not be used to introduce a new diagnosis");
  }
  if (options.length - 2 < 2) {
    problems.push("needs at least two clinically reasonable choices besides Other / Unable to determine");
  }

  if (!stem.includes("?") && !text.includes("clarify")) {
    problems.push("must ask a question (end with '?' or ask the provider to clarify)");
  }
  const length = [...stem].length;
  if (length > MAX_STEM_CHARS) problems.push(`too long (${length} chars, max ${MAX_STEM_CHARS})`);
  return { ok: problems.length === 0, problems };
}
