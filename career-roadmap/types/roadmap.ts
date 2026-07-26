export type ResumeInput =
  | { kind: "file"; file: File }
  | { kind: "text"; value: string };

export type JDInput = {
  name: string;
} & ({ kind: "file"; file: File } | { kind: "text"; value: string } | { kind: "empty" });

export type Answers = {
  proudOf: string;
  heldBack: string;
  whyTheseRoles: string;
  timeframe: string;
  catchAll: string;
};

export const EMPTY_ANSWERS: Answers = {
  proudOf: "",
  heldBack: "",
  whyTheseRoles: "",
  timeframe: "",
  catchAll: "",
};

export type StepId = "upload" | "questions" | "processing" | "results" | "error";

export type StepperState = {
  step: StepId;
  resume: ResumeInput | null;
  jds: [JDInput, JDInput, JDInput];
  answers: Answers;
  email: string;
  streamedText: string;
  errorMessage: string | null;
};

/** A single parsed job description, as sent to the server and to the prompt builder. */
export type JobDescription = {
  name: string | null;
  text: string;
};

/** Row shape for the `runs` analytics table — only ever these fields, never raw text. */
export type RunRecord = {
  email: string | null;
  role_categories: string[];
  summary_findings: string[];
  prompt_version: string;
};
