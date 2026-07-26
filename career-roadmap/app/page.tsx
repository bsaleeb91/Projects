import Link from "next/link";
import { Hero } from "@/components/landing/Hero";
import { CreatorStory } from "@/components/landing/CreatorStory";
import { DataNote } from "@/components/landing/DataNote";
import { HERO_CTA } from "@/lib/content/landing-copy";

export default function LandingPage() {
  return (
    <main className="flex-1">
      <Hero />
      <div className="mx-auto max-w-[65ch] px-6">
        <hr className="border-line" />
      </div>
      <CreatorStory />
      <div className="mx-auto max-w-[65ch] px-6 pb-12">
        <DataNote />
      </div>
      <div className="mx-auto flex max-w-[65ch] justify-center px-6 pb-24">
        <Link
          href="/tool"
          className="inline-flex items-center justify-center rounded-md bg-accent px-6 py-3 text-[0.95rem] font-medium text-white transition-colors hover:bg-accent/90 motion-reduce:transition-none"
        >
          {HERO_CTA}
        </Link>
      </div>
    </main>
  );
}
