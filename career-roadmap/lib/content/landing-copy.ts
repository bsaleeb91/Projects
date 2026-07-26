/**
 * All landing-page and data-handling copy lives here, not inline in JSX —
 * this is first-person narrative about a real career, and it should be a
 * single-file diff to revise wording without touching component logic.
 *
 * The founder-story paragraphs below are a first draft written from the
 * facts of the build history (five 0-to-1 builds, non-linear career path).
 * Review and edit in your own voice before this goes live — it's your story,
 * told in your words, not a generated pitch.
 */

export const HERO_HEADLINE =
  "Where you are, where these roles need you to be, and the bridge between them.";

export const HERO_SUBHEAD =
  "Upload your resume and three job descriptions for roles you want. Answer five questions. Get back a written roadmap — gap-first, evidence-based, and specific enough to act on.";

export const HERO_CTA = "Start your roadmap";

export const CREATOR_STORY_PARAGRAPHS: string[] = [
  "I've built the same thing five times, in five very different kinds of places: a large healthcare system, an MBA internship, a health information network, my own consulting practice, and a specialty pharmacy's data team. Each time, there was no function to inherit and no playbook to follow — just a real problem and a blank slate — and the job was to figure out what needed to exist, then build it.",
  "That's only possible because my own path didn't run in a straight line. I started in biology and public health, moved into mergers and acquisitions and corporate development, then into the operational details of specialty pharmacy, and now into data and AI strategy. None of those moves followed obviously from the one before it. I don't say that as a disclaimer — it's the reason this method exists. You don't learn to find the bridge between where you are and where you're going by staying on one path the whole way. You learn it by crossing between paths, more than once, and working out each time what actually transfers and what has to be built from scratch.",
  "The roadmap this tool produces uses that same method: figure out, concretely, where you actually stand — not what your title says, but what you've actually built and demonstrated. Figure out, just as concretely, what the roles you want actually require. Then name the specific bridge between the two. No generic encouragement dressed up as a plan — just the gap, stated plainly, and the fastest realistic way to close it.",
];

export const DATA_HANDLING_NOTE =
  "I track how many people use this and what kinds of roles they're targeting, so I can see whether this is working across different situations. I don't store your resume, your job descriptions, or the roadmap itself — that raw material never sticks around past generating your result.";
