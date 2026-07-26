import type { Answers, JobDescription } from "@/types/roadmap";

/**
 * Builds the per-request user prompt. Unique every time (resume/JDs/answers
 * all vary) — deliberately NOT cache-annotated, unlike the static system
 * prompt, since a per-request cache_control breakpoint here would never hit.
 */
export function buildUserPrompt(
  resumeText: string,
  jds: [JobDescription, JobDescription, JobDescription],
  answers: Answers,
): string {
  const jdSection = (jd: JobDescription, index: number) =>
    `## Job Description ${index + 1}${jd.name ? ` — ${jd.name}` : ""}\n${jd.text}`;

  return `## Resume
${resumeText}

${jdSection(jds[0], 0)}

${jdSection(jds[1], 1)}

${jdSection(jds[2], 2)}

## Candidate's Answers

1. What they're most proud of in their current or last role:
${answers.proudOf}

2. What they believe is actually holding them back right now (compare this against the resume and job description evidence — see the self-diagnosis instruction):
${answers.heldBack}

3. Why these three roles specifically:
${answers.whyTheseRoles}

4. Their stated timeframe (this must drive Part D's phasing):
${answers.timeframe}

5. Anything else about their situation a resume wouldn't show:
${answers.catchAll.trim() || "(not provided)"}

Produce the roadmap now, following the Part A through E structure and all tone and method instructions above.`;
}
