"use client";

import { useReducer } from "react";
import { UploadStep } from "@/components/stepper/steps/UploadStep";
import { QuestionsStep } from "@/components/stepper/steps/QuestionsStep";
import { ProcessingStep } from "@/components/stepper/steps/ProcessingStep";
import { ResultsStep } from "@/components/stepper/steps/ResultsStep";
import { ProgressDots } from "@/components/ui/ProgressDots";
import { Button } from "@/components/ui/Button";
import { EMPTY_ANSWERS, type Answers, type JDInput, type StepperState } from "@/types/roadmap";
import type { FileOrText } from "@/components/ui/FileDrop";

type Action =
  | { type: "SET_STEP"; step: "upload" | "questions" }
  | { type: "SET_RESUME"; value: FileOrText | null }
  | { type: "SET_JD"; index: 0 | 1 | 2; value: FileOrText | null }
  | { type: "SET_JD_NAME"; index: 0 | 1 | 2; name: string }
  | { type: "SET_ANSWER"; field: keyof Answers; value: string }
  | { type: "SET_EMAIL"; value: string }
  | { type: "SUBMIT" }
  | { type: "APPEND_CHUNK"; text: string }
  | { type: "COMPLETE" }
  | { type: "SET_ERROR"; message: string };

type State = StepperState & { formData: FormData | null };

const initialState: State = {
  step: "upload",
  resume: null,
  jds: [
    { kind: "empty", name: "" },
    { kind: "empty", name: "" },
    { kind: "empty", name: "" },
  ],
  answers: EMPTY_ANSWERS,
  email: "",
  streamedText: "",
  errorMessage: null,
  formData: null,
};

function buildFormData(state: State): FormData {
  const formData = new FormData();

  if (state.resume?.kind === "file") formData.set("resumeFile", state.resume.file);
  if (state.resume?.kind === "text") formData.set("resumeText", state.resume.value);

  state.jds.forEach((jd, i) => {
    formData.set(`jd${i}Name`, jd.name);
    if (jd.kind === "file") formData.set(`jd${i}File`, jd.file);
    if (jd.kind === "text") formData.set(`jd${i}Text`, jd.value);
  });

  formData.set("answers", JSON.stringify(state.answers));
  formData.set("email", state.email);

  return formData;
}

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case "SET_STEP":
      return { ...state, step: action.step };
    case "SET_RESUME":
      return { ...state, resume: action.value };
    case "SET_JD": {
      const jds = [...state.jds] as State["jds"];
      const name = jds[action.index].name;
      jds[action.index] = (action.value
        ? { ...action.value, name }
        : { kind: "empty", name }) as JDInput;
      return { ...state, jds };
    }
    case "SET_JD_NAME": {
      const jds = [...state.jds] as State["jds"];
      jds[action.index] = { ...jds[action.index], name: action.name } as JDInput;
      return { ...state, jds };
    }
    case "SET_ANSWER":
      return { ...state, answers: { ...state.answers, [action.field]: action.value } };
    case "SET_EMAIL":
      return { ...state, email: action.value };
    case "SUBMIT":
      return { ...state, step: "processing", formData: buildFormData(state) };
    case "APPEND_CHUNK":
      return { ...state, streamedText: state.streamedText + action.text };
    case "COMPLETE":
      return { ...state, step: "results" };
    case "SET_ERROR":
      return { ...state, step: "error", errorMessage: action.message };
    default:
      return state;
  }
}

export function StepperApp() {
  const [state, dispatch] = useReducer(reducer, initialState);

  const stepIndex = { upload: 0, questions: 1, processing: 2, results: 2, error: 2 }[
    state.step
  ];

  return (
    <div className="flex-1">
      <div className="no-print mx-auto max-w-2xl px-6 pt-8">
        <ProgressDots activeIndex={stepIndex} />
      </div>

      {state.step === "upload" && (
        <UploadStep
          resume={state.resume}
          jds={state.jds}
          onResumeChange={(value) => dispatch({ type: "SET_RESUME", value })}
          onJDChange={(index, value) => dispatch({ type: "SET_JD", index, value })}
          onJDNameChange={(index, name) => dispatch({ type: "SET_JD_NAME", index, name })}
          onContinue={() => dispatch({ type: "SET_STEP", step: "questions" })}
        />
      )}

      {state.step === "questions" && (
        <QuestionsStep
          answers={state.answers}
          email={state.email}
          onChange={(field, value) => dispatch({ type: "SET_ANSWER", field, value })}
          onEmailChange={(value) => dispatch({ type: "SET_EMAIL", value })}
          onBack={() => dispatch({ type: "SET_STEP", step: "upload" })}
          onSubmit={() => dispatch({ type: "SUBMIT" })}
        />
      )}

      {state.step === "processing" && state.formData && (
        <ProcessingStep
          formData={state.formData}
          streamedText={state.streamedText}
          onChunk={(text) => dispatch({ type: "APPEND_CHUNK", text })}
          onComplete={() => dispatch({ type: "COMPLETE" })}
          onError={(message) => dispatch({ type: "SET_ERROR", message })}
        />
      )}

      {state.step === "results" && <ResultsStep text={state.streamedText} />}

      {state.step === "error" && (
        <div className="mx-auto flex max-w-2xl flex-col gap-4 px-6 py-16">
          <h2 className="font-display text-h2 text-ink">Something went wrong</h2>
          <p className="text-body-lg text-ink-muted">{state.errorMessage}</p>
          <div>
            <Button onClick={() => dispatch({ type: "SET_STEP", step: "upload" })}>
              Start over
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
