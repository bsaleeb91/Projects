import { CREATOR_STORY_PARAGRAPHS } from "@/lib/content/landing-copy";

export function CreatorStory() {
  return (
    <section className="mx-auto flex max-w-[65ch] flex-col gap-5 px-6 py-12">
      {CREATOR_STORY_PARAGRAPHS.map((paragraph, i) => (
        <p key={i} className="text-body-lg text-ink">
          {paragraph}
        </p>
      ))}
    </section>
  );
}
