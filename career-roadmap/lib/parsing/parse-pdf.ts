import { PDFParse } from "pdf-parse";
import { DocumentParseError, MIN_EXTRACTED_TEXT_LENGTH, type ParseField } from "./errors";

/**
 * Extracts plain text from a PDF buffer. Throws a `DocumentParseError` with a
 * specific, user-facing message (always pointing at the paste-text fallback)
 * on any failure — corrupt file, password protection, or a scanned/image-only
 * PDF that "parses" but yields no real text.
 */
export async function parsePdf(buffer: Buffer, field: ParseField): Promise<string> {
  let parser: PDFParse | null = null;
  try {
    parser = new PDFParse({ data: buffer });
    const result = await parser.getText();
    const text = result.text.trim();

    if (text.length < MIN_EXTRACTED_TEXT_LENGTH) {
      throw new DocumentParseError(
        "We couldn't find readable text in that PDF — it may be a scanned image rather than real text. Try pasting the text instead.",
        field,
      );
    }

    return text;
  } catch (err) {
    if (err instanceof DocumentParseError) throw err;
    console.error("[parse-pdf] underlying parse failure", err);
    throw new DocumentParseError(
      "We couldn't read that PDF — it may be corrupted or password-protected. Try pasting the text instead.",
      field,
    );
  } finally {
    await parser?.destroy();
  }
}
