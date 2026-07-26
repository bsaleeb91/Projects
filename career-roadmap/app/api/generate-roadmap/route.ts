import { NextRequest, after } from "next/server";
import { anthropic, MODELS } from "@/lib/anthropic";
import { buildSystemPrompt, PROMPT_VERSION } from "@/lib/prompts/roadmap-system";
import { buildUserPrompt } from "@/lib/prompts/roadmap-user";
import { parsePdf } from "@/lib/parsing/parse-pdf";
import { parseDocx } from "@/lib/parsing/parse-docx";
import { DocumentParseError, type ParseField } from "@/lib/parsing/errors";
import { validateGenerateRequest } from "@/lib/validation";
import { recordAnalyticsInBackground } from "@/lib/analytics";
import type { Answers, JobDescription } from "@/types/roadmap";

// pdf-parse/mammoth need Node APIs — not available on the edge runtime.
export const runtime = "nodejs";
// Long-form generation can take a couple of minutes — requires Fluid Compute
// enabled on the Vercel project (dashboard setting, not configurable here).
export const maxDuration = 300;

/** Reads a resume/JD field that may have arrived as a file OR pasted text,
 * parsing the file server-side if present. Throws DocumentParseError on any
 * failure, always pointing the user at the paste-text fallback. */
async function extractFieldText(
  formData: FormData,
  field: ParseField,
  filePrefix: string,
  textPrefix: string,
): Promise<string> {
  const file = formData.get(filePrefix);
  const pastedText = formData.get(textPrefix);

  if (file instanceof File && file.size > 0) {
    const buffer = Buffer.from(await file.arrayBuffer());
    const name = file.name.toLowerCase();
    if (file.type === "application/pdf" || name.endsWith(".pdf")) {
      return parsePdf(buffer, field);
    }
    if (
      name.endsWith(".docx") ||
      name.endsWith(".doc") ||
      file.type.includes("word") ||
      file.type.includes("officedocument")
    ) {
      return parseDocx(buffer, field);
    }
    throw new DocumentParseError(
      "That file type isn't supported. Try uploading a PDF or Word file, or paste the text instead.",
      field,
    );
  }

  if (typeof pastedText === "string" && pastedText.trim().length > 0) {
    return pastedText.trim();
  }

  throw new DocumentParseError("Missing content.", field);
}

export async function POST(req: NextRequest) {
  const formData = await req.formData();

  // Defensive re-check — the client already gates this, but never trust it
  // alone. Fail fast, before any parsing or Anthropic call.
  const validation = validateGenerateRequest(formData);
  if (!validation.valid) {
    return Response.json(
      { error: validation.error, field: validation.field },
      { status: 400 },
    );
  }

  let resumeText: string;
  let jds: [JobDescription, JobDescription, JobDescription];

  try {
    resumeText = await extractFieldText(formData, "resume", "resumeFile", "resumeText");

    const parsedJds = await Promise.all(
      ([0, 1, 2] as const).map(async (i) => {
        const text = await extractFieldText(
          formData,
          `jd${i}` as ParseField,
          `jd${i}File`,
          `jd${i}Text`,
        );
        const rawName = formData.get(`jd${i}Name`);
        const name = typeof rawName === "string" && rawName.trim() ? rawName.trim() : null;
        return { name, text };
      }),
    );
    jds = parsedJds as [JobDescription, JobDescription, JobDescription];
  } catch (err) {
    if (err instanceof DocumentParseError) {
      return Response.json({ error: err.userMessage, field: err.field }, { status: 400 });
    }
    return Response.json(
      { error: "Something went wrong reading your documents. Please try again." },
      { status: 400 },
    );
  }

  const rawAnswers = formData.get("answers");
  const answers = JSON.parse(rawAnswers as string) as Answers;
  const rawEmail = formData.get("email");
  const email = typeof rawEmail === "string" && rawEmail.trim() ? rawEmail.trim() : null;

  const systemPrompt = buildSystemPrompt();
  const userPrompt = buildUserPrompt(resumeText, jds, answers);
  const encoder = new TextEncoder();

  // Shared between start()/cancel() so a client disconnect can abort the
  // in-flight Anthropic call instead of letting it run to completion.
  let anthropicStreamRef: ReturnType<typeof anthropic.messages.stream> | null = null;
  let streamClosed = false;

  const stream = new ReadableStream({
    async start(controller) {
      let fullText = "";
      try {
        const anthropicStream = anthropic.messages.stream({
          model: MODELS.roadmap,
          max_tokens: 8000,
          system: [
            { type: "text", text: systemPrompt, cache_control: { type: "ephemeral" } },
          ],
          messages: [{ role: "user", content: userPrompt }],
        });
        anthropicStreamRef = anthropicStream;

        anthropicStream.on("text", (delta) => {
          fullText += delta;
          if (streamClosed) return;
          controller.enqueue(encoder.encode(delta));
        });

        await anthropicStream.finalMessage();
        streamClosed = true;
        controller.close();

        // Scheduled via after() so it survives past the response being sent —
        // the function can otherwise be torn down the moment the stream
        // finishes. This is the only point with access to resumeText/jds/
        // fullText; recordAnalyticsInBackground never persists them, only
        // the short derived fields it produces.
        after(() =>
          recordAnalyticsInBackground({
            jds,
            answers,
            fullRoadmapText: fullText,
            promptVersion: PROMPT_VERSION,
            email,
          }).catch((e) => console.error("[analytics] failed to record run", e)),
        );
      } catch (err) {
        if (streamClosed) {
          // Client disconnected — cancel() already aborted the Anthropic
          // call and closed things down; this rejection is expected, not
          // a real failure.
          return;
        }
        console.error("[generate-roadmap] generation failed", err);
        streamClosed = true;
        controller.error(err instanceof Error ? err : new Error(String(err)));
      }
    },
    cancel() {
      // The user closed the tab or navigated away mid-generation — stop
      // the Anthropic call instead of letting it run (and bill) to
      // completion for output nobody will read.
      streamClosed = true;
      anthropicStreamRef?.abort();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/plain; charset=utf-8",
      "Cache-Control": "no-cache",
      "X-Prompt-Version": PROMPT_VERSION,
    },
  });
}
