"use client";

import { useEffect, useRef } from "react";

type Props = {
  formData: FormData;
  streamedText: string;
  onChunk: (text: string) => void;
  onComplete: () => void;
  onError: (message: string) => void;
};

export function ProcessingStep({ formData, streamedText, onChunk, onComplete, onError }: Props) {
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    (async () => {
      try {
        const res = await fetch("/api/generate-roadmap", { method: "POST", body: formData });

        if (!res.ok) {
          const body = (await res.json().catch(() => null)) as { error?: string } | null;
          onError(body?.error ?? "Something went wrong. Please try again.");
          return;
        }
        if (!res.body) {
          onError("Something went wrong. Please try again.");
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          onChunk(decoder.decode(value, { stream: true }));
        }
        onComplete();
      } catch {
        onError("Lost connection while generating your roadmap. Please try again.");
      }
    })();
    // formData/onChunk/onComplete/onError are stable for the lifetime of this
    // mount — this effect is intentionally run-once (guarded by startedRef).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="mx-auto flex max-w-2xl flex-col gap-6 px-6 py-16">
      <div className="flex flex-col gap-2">
        <h2 className="font-display text-h2 text-ink">Building your roadmap</h2>
        <p className="text-body-lg text-ink-muted">
          This takes a minute or two — reading your resume and all three roles closely, rather
          than skimming. It&apos;ll appear below as it&apos;s written.
        </p>
      </div>
      <div className="flex items-center gap-2 text-meta text-ink-muted">
        <span className="h-2 w-2 animate-pulse rounded-full bg-accent motion-reduce:animate-none" />
        Generating
      </div>
      {streamedText && (
        <div className="whitespace-pre-wrap rounded-md border border-line bg-paper-muted p-6 text-[0.95rem] leading-relaxed text-ink-muted">
          {streamedText}
        </div>
      )}
    </div>
  );
}
