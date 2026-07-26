import mammoth from "mammoth";
import { DocumentParseError, MIN_EXTRACTED_TEXT_LENGTH, type ParseField } from "./errors";

/**
 * Extracts plain text from a DOCX buffer via mammoth. Throws a `DocumentParseError`
 * with a specific, user-facing message pointing at the paste-text fallback on
 * any failure, including a "successful" parse that yields near-empty text.
 */
export async function parseDocx(buffer: Buffer, field: ParseField): Promise<string> {
  try {
    const result = await mammoth.extractRawText({ buffer });
    const text = result.value.trim();

    if (text.length < MIN_EXTRACTED_TEXT_LENGTH) {
      throw new DocumentParseError(
        "We couldn't find readable text in that Word file. Try pasting the text instead.",
        field,
      );
    }

    return text;
  } catch (err) {
    if (err instanceof DocumentParseError) throw err;
    throw new DocumentParseError(
      "We couldn't read that Word file — it may be corrupted or in an unsupported format. Try pasting the text instead.",
      field,
    );
  }
}
