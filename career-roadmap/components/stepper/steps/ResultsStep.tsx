import Link from "next/link";
import { CopyPrintBar } from "@/components/ui/CopyPrintBar";

export function ResultsStep({ text }: { text: string }) {
  return (
    <div className="mx-auto flex max-w-[65ch] flex-col gap-8 px-6 py-16">
      <div className="no-print flex items-center justify-between">
        <h2 className="font-display text-h2 text-ink">Your roadmap</h2>
        <CopyPrintBar text={text} />
      </div>
      <article className="whitespace-pre-wrap text-body-lg leading-relaxed text-ink">
        {text}
      </article>
      <div className="no-print border-t border-line pt-6">
        <Link href="/tool" className="text-meta text-ink-muted hover:text-accent">
          Start over
        </Link>
      </div>
    </div>
  );
}
