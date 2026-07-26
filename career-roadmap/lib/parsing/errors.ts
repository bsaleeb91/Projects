export type ParseField = "resume" | "jd0" | "jd1" | "jd2";

/**
 * Thrown whenever a document can't be turned into usable text. `userMessage` is
 * shown directly in the UI next to the offending field — always specific, and
 * always pointing at the paste-text fallback (see product spec §6).
 */
export class DocumentParseError extends Error {
  constructor(
    public userMessage: string,
    public field: ParseField,
  ) {
    super(userMessage);
    this.name = "DocumentParseError";
  }
}

/** Somewhat arbitrary, but a resume/JD that parses to fewer than this many
 * characters is almost certainly a scanned image or a parsing failure, not a
 * real (if short) document — treat it as a parse failure rather than silently
 * sending near-empty text to the model. */
export const MIN_EXTRACTED_TEXT_LENGTH = 40;
