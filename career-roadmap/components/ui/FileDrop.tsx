"use client";

import { useId, useState } from "react";

export type FileOrText = { kind: "file"; file: File } | { kind: "text"; value: string };

type Props = {
  label: string;
  accept: string;
  value: FileOrText | null;
  onChange: (value: FileOrText | null) => void;
  error?: string;
  placeholder?: string;
};

/**
 * Shared resume/JD input: a paste-text textarea (the primary, most-likely
 * path per spec) with a toggle to switch to file upload instead. Only one of
 * file/text is ever active at a time.
 */
export function FileDrop({ label, accept, value, onChange, error, placeholder }: Props) {
  const [mode, setMode] = useState<"text" | "file">(value?.kind === "file" ? "file" : "text");
  const textId = useId();
  const fileId = useId();

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-ink">{label}</span>
        <div className="flex gap-1 text-meta">
          <button
            type="button"
            onClick={() => {
              setMode("text");
              onChange(null);
            }}
            className={`rounded px-2 py-1 ${
              mode === "text" ? "bg-accent-soft text-accent" : "text-ink-muted hover:text-ink"
            }`}
          >
            Paste text
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("file");
              onChange(null);
            }}
            className={`rounded px-2 py-1 ${
              mode === "file" ? "bg-accent-soft text-accent" : "text-ink-muted hover:text-ink"
            }`}
          >
            Upload file
          </button>
        </div>
      </div>

      {mode === "text" ? (
        <textarea
          id={textId}
          rows={6}
          placeholder={placeholder}
          value={value?.kind === "text" ? value.value : ""}
          onChange={(e) => onChange({ kind: "text", value: e.target.value })}
          className="w-full rounded-md border border-line bg-paper px-3 py-2.5 text-[0.95rem] leading-relaxed text-ink outline-none placeholder:text-ink-muted"
        />
      ) : (
        <label
          htmlFor={fileId}
          className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed border-line bg-paper-muted px-3 py-8 text-center hover:border-accent"
        >
          <span className="text-sm text-ink">
            {value?.kind === "file" ? value.file.name : "Click to choose a file"}
          </span>
          <span className="text-meta text-ink-muted">{accept.replaceAll(",", ", ")}</span>
          <input
            id={fileId}
            type="file"
            accept={accept}
            className="sr-only"
            onChange={(e) => {
              const file = e.target.files?.[0];
              onChange(file ? { kind: "file", file } : null);
            }}
          />
        </label>
      )}

      {error && <p className="text-meta text-red-600">{error}</p>}
    </div>
  );
}
