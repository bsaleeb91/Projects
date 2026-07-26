import type { Answers, JDInput, ResumeInput } from "@/types/roadmap";

const MIN_TEXT_LENGTH = 10;

function inputHasContent(input: ResumeInput | JDInput | null): boolean {
  if (!input) return false;
  if (input.kind === "empty") return false;
  if (input.kind === "text") return input.value.trim().length >= MIN_TEXT_LENGTH;
  return input.file.size > 0;
}

export function isUploadStepValid(
  resume: ResumeInput | null,
  jds: [JDInput, JDInput, JDInput],
): boolean {
  return inputHasContent(resume) && jds.every(inputHasContent);
}

export function isQuestionsStepValid(answers: Answers): boolean {
  return (
    answers.proudOf.trim().length >= MIN_TEXT_LENGTH &&
    answers.heldBack.trim().length >= MIN_TEXT_LENGTH &&
    answers.whyTheseRoles.trim().length >= MIN_TEXT_LENGTH &&
    answers.timeframe.trim().length > 0
  );
}
