export type RoadmapSection = { heading: string; body: string };

const HEADING_RE = /^#{1,6}\s+(.+)$/;

/**
 * Splits the model's markdown-style output (it's instructed to use
 * `### Part A: ...` headings) into heading/body pairs so the results page
 * can render real typographic hierarchy instead of showing literal `#`
 * characters. Deliberately simple — this only strips heading markers; it
 * doesn't pull in a markdown renderer, matching the prompt's own
 * "no tables, no charts, no visual notation" instruction to the model.
 */
export function parseRoadmapSections(text: string): RoadmapSection[] {
  const lines = text.split("\n");
  const sections: RoadmapSection[] = [];
  let bodyLines: string[] = [];
  let pendingHeading: string | null = null;

  const flush = (heading: string) => {
    sections.push({ heading, body: bodyLines.join("\n").trim() });
    bodyLines = [];
  };

  for (const line of lines) {
    const match = line.match(HEADING_RE);
    if (match) {
      if (pendingHeading !== null) flush(pendingHeading);
      pendingHeading = match[1].trim();
    } else {
      bodyLines.push(line);
    }
  }

  if (pendingHeading !== null) {
    flush(pendingHeading);
  } else if (bodyLines.join("").trim().length > 0) {
    // The model didn't use headings at all — fall back to one untitled
    // section with everything, so nothing is silently dropped.
    sections.push({ heading: "", body: bodyLines.join("\n").trim() });
  }

  return sections;
}
