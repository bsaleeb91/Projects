import type { Answers } from "@/types/roadmap";

const MIN_TEXT_LENGTH = 10;

export type ValidationResult =
  | { valid: true }
  | { valid: false; error: string; field?: string };

function hasContent(value: FormDataEntryValue | null): boolean {
  if (value === null) return false;
  if (typeof value === "string") return value.trim().length >= MIN_TEXT_LENGTH;
  // File
  return value.size > 0;
}

/**
 * Defensive server-side re-check of the same rules the client already enforces
 * (resume present, exactly 3 JDs present, Q1-Q4 answered) — exists because the
 * client can be bypassed (devtools, a direct API call, disabled JS). Runs
 * before any file parsing or Anthropic call, so a bad request fails fast with
 * no wasted cost.
 */
export function validateGenerateRequest(formData: FormData): ValidationResult {
  const resumeOk =
    hasContent(formData.get("resumeFile")) || hasContent(formData.get("resumeText"));
  if (!resumeOk) {
    return { valid: false, error: "A resume is required.", field: "resume" };
  }

  for (const i of [0, 1, 2] as const) {
    const ok =
      hasContent(formData.get(`jd${i}File`)) || hasContent(formData.get(`jd${i}Text`));
    if (!ok) {
      return {
        valid: false,
        error: "All three job descriptions are required.",
        field: `jd${i}`,
      };
    }
  }

  const rawAnswers = formData.get("answers");
  if (typeof rawAnswers !== "string") {
    return { valid: false, error: "Missing answers.", field: "answers" };
  }

  let answers: Partial<Answers>;
  try {
    answers = JSON.parse(rawAnswers);
  } catch {
    return { valid: false, error: "Malformed answers payload.", field: "answers" };
  }

  const required: (keyof Answers)[] = [
    "proudOf",
    "heldBack",
    "whyTheseRoles",
    "timeframe",
  ];
  for (const key of required) {
    if (!answers[key] || answers[key]!.trim().length === 0) {
      return { valid: false, error: `Answer "${key}" is required.`, field: key };
    }
  }

  return { valid: true };
}
