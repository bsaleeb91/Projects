import Link from "next/link";
import { HERO_HEADLINE, HERO_SUBHEAD, HERO_CTA } from "@/lib/content/landing-copy";

export function Hero() {
  return (
    <section className="mx-auto flex max-w-3xl flex-col gap-6 px-6 pt-20 pb-12 text-center sm:pt-28">
      <h1 className="font-display text-[2.25rem] leading-[1.1] tracking-tight text-ink sm:text-display sm:leading-[1.05]">
        {HERO_HEADLINE}
      </h1>
      <p className="text-body-lg text-ink-muted">{HERO_SUBHEAD}</p>
      <div className="mt-2 flex justify-center">
        <Link
          href="/tool"
          className="inline-flex items-center justify-center rounded-md bg-accent px-6 py-3 text-[0.95rem] font-medium text-white transition-colors hover:bg-accent/90 motion-reduce:transition-none"
        >
          {HERO_CTA}
        </Link>
      </div>
    </section>
  );
}
