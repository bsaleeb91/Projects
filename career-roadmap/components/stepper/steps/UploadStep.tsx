"use client";

import { FileDrop, type FileOrText } from "@/components/ui/FileDrop";
import { Button } from "@/components/ui/Button";
import { DataNote } from "@/components/landing/DataNote";
import { isUploadStepValid } from "@/components/stepper/validation";
import type { JDInput, ResumeInput } from "@/types/roadmap";

const ACCEPT = ".pdf,.doc,.docx";

type Props = {
  resume: ResumeInput | null;
  jds: [JDInput, JDInput, JDInput];
  onResumeChange: (value: FileOrText | null) => void;
  onJDChange: (index: 0 | 1 | 2, value: FileOrText | null) => void;
  onJDNameChange: (index: 0 | 1 | 2, name: string) => void;
  onContinue: () => void;
};

function toFileOrText(input: ResumeInput | JDInput | null): FileOrText | null {
  if (!input || input.kind === "empty") return null;
  return input;
}

export function UploadStep({
  resume,
  jds,
  onResumeChange,
  onJDChange,
  onJDNameChange,
  onContinue,
}: Props) {
  const valid = isUploadStepValid(resume, jds);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-10 px-6 py-12">
      <div className="flex flex-col gap-2">
        <h2 className="font-display text-h2 text-ink">Upload your resume and three roles</h2>
        <p className="text-body-lg text-ink-muted">
          Paste is usually fastest — copy straight from your resume or a job posting. Three
          job descriptions, because the pattern across all three is what makes this useful.
        </p>
      </div>

      <FileDrop
        label="Resume"
        accept={ACCEPT}
        value={toFileOrText(resume)}
        onChange={onResumeChange}
        placeholder="Paste your resume text here"
      />

      <div className="flex flex-col gap-6">
        {([0, 1, 2] as const).map((i) => (
          <div key={i} className="flex flex-col gap-2 rounded-md border border-line p-4">
            <input
              type="text"
              aria-label={`Job Description ${i + 1} name (optional)`}
              placeholder='Optional name, e.g. "Director of Strategy"'
              value={jds[i].name}
              onChange={(e) => onJDNameChange(i, e.target.value)}
              className="w-full border-b border-line bg-transparent pb-2 text-sm text-ink outline-none placeholder:text-ink-muted"
            />
            <FileDrop
              label={`Job Description ${i + 1}`}
              accept={ACCEPT}
              value={toFileOrText(jds[i])}
              onChange={(value) => onJDChange(i, value)}
              placeholder="Paste the job description text here"
            />
          </div>
        ))}
      </div>

      <DataNote />

      <div className="flex justify-end">
        <Button onClick={onContinue} disabled={!valid}>
          Continue
        </Button>
      </div>
    </div>
  );
}
