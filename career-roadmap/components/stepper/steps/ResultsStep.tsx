import Link from "next/link";
import { CopyPrintBar } from "@/components/ui/CopyPrintBar";
import { parseRoadmapSections } from "@/lib/parseRoadmapSections";

/** Renders `**bold**` spans as real emphasis instead of literal asterisks —
 * the model isn't told to use inline markdown, but it's a common enough
 * habit (e.g. bolding a role name in Part C) that it shows up in practice. */
function renderInlineBold(body: string) {
  return body.split(/(\*\*[^*]+\*\*)/g).map((part, i) => {
    const match = part.match(/^\*\*([^*]+)\*\*$/);
    return match ? <strong key={i}>{match[1]}</strong> : part;
  });
}

export function ResultsStep({ text }: { text: string }) {
  const sections = parseRoadmapSections(text);

  return (
    <div className="mx-auto flex max-w-[65ch] flex-col gap-8 px-6 py-16">
      <div className="no-print flex items-center justify-between">
        <h2 className="font-display text-h2 text-ink">Your roadmap</h2>
        <CopyPrintBar text={text} />
      </div>
      <article className="flex flex-col gap-10">
        {sections.map((section, i) => (
          <section key={i} className="flex flex-col gap-3">
            {section.heading && (
              <h3 className="font-display text-h3 text-ink">{section.heading}</h3>
            )}
            <div className="whitespace-pre-wrap text-body-lg text-ink">
              {renderInlineBold(section.body)}
            </div>
          </section>
        ))}
      </article>
      <div className="no-print border-t border-line pt-6">
        <Link href="/tool" className="text-meta text-ink-muted hover:text-accent">
          Start over
        </Link>
      </div>
    </div>
  );
}
