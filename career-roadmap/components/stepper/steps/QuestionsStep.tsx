"use client";

import { TextArea } from "@/components/ui/TextArea";
import { Button } from "@/components/ui/Button";
import { isQuestionsStepValid } from "@/components/stepper/validation";
import type { Answers } from "@/types/roadmap";

const TIMEFRAME_PRESETS = ["3 months", "6 months", "1 year", "2+ years"];

type Props = {
  answers: Answers;
  email: string;
  onChange: (field: keyof Answers, value: string) => void;
  onEmailChange: (value: string) => void;
  onBack: () => void;
  onSubmit: () => void;
};

export function QuestionsStep({
  answers,
  email,
  onChange,
  onEmailChange,
  onBack,
  onSubmit,
}: Props) {
  const valid = isQuestionsStepValid(answers);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-8 px-6 py-12">
      <div className="flex flex-col gap-2">
        <h2 className="font-display text-h2 text-ink">Five questions</h2>
        <p className="text-body-lg text-ink-muted">
          These capture what a resume and a job description can&apos;t.
        </p>
      </div>

      <TextArea
        id="proudOf"
        label="1. What are you most proud of in your current or last role?"
        hint="Resumes list responsibilities, not what mattered. This is your real signal."
        rows={3}
        value={answers.proudOf}
        onChange={(e) => onChange("proudOf", e.target.value)}
      />

      <TextArea
        id="heldBack"
        label="2. What do you think is actually holding you back from these roles right now?"
        hint="Your answer here gets checked against the evidence — the gap between the two is often the real finding."
        rows={3}
        value={answers.heldBack}
        onChange={(e) => onChange("heldBack", e.target.value)}
      />

      <TextArea
        id="whyTheseRoles"
        label="3. Why these three roles specifically?"
        hint="This tells us whether they're a coherent direction or scattered."
        rows={3}
        value={answers.whyTheseRoles}
        onChange={(e) => onChange("whyTheseRoles", e.target.value)}
      />

      <div className="flex flex-col gap-2">
        <TextArea
          id="timeframe"
          label="4. What's your timeframe?"
          hint="This changes how aggressive or patient the roadmap should be."
          rows={2}
          value={answers.timeframe}
          onChange={(e) => onChange("timeframe", e.target.value)}
        />
        <div className="flex flex-wrap gap-2">
          {TIMEFRAME_PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => onChange("timeframe", preset)}
              className="rounded-full border border-line px-3 py-1 text-meta text-ink-muted hover:border-accent hover:text-accent"
            >
              {preset}
            </button>
          ))}
        </div>
      </div>

      <TextArea
        id="catchAll"
        label="5. Anything else about your situation a resume wouldn't show?"
        hint="Optional."
        rows={3}
        value={answers.catchAll}
        onChange={(e) => onChange("catchAll", e.target.value)}
      />

      <div className="flex flex-col gap-1.5 border-t border-line pt-6">
        <label htmlFor="email" className="text-sm font-medium text-ink">
          Email (optional)
        </label>
        <p className="text-meta text-ink-muted">
          Not required, and not used to send you anything — just lets us tie usage to a person
          if that&apos;s ever useful. Leave it blank if you&apos;d rather not.
        </p>
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => onEmailChange(e.target.value)}
          placeholder="you@example.com"
          className="w-full max-w-sm rounded-md border border-line bg-paper px-3 py-2 text-[0.95rem] text-ink outline-none placeholder:text-ink-muted"
        />
      </div>

      <div className="flex justify-between">
        <Button variant="secondary" onClick={onBack}>
          Back
        </Button>
        <Button onClick={onSubmit} disabled={!valid}>
          Generate my roadmap
        </Button>
      </div>
    </div>
  );
}
