import { anthropic, MODELS } from "@/lib/anthropic";
import { getSupabase } from "@/lib/supabase";
import type { Answers, JobDescription } from "@/types/roadmap";

/**
 * Classifies each of the three job descriptions into a short, normalized role
 * category (e.g. "Director of Strategy", "Data/Analytics Leadership") — never
 * the raw JD text itself. Cheap Haiku classification task, structured output.
 */
async function extractRoleCategories(
  jds: [JobDescription, JobDescription, JobDescription],
): Promise<string[]> {
  const response = await anthropic.messages.create({
    model: MODELS.analytics,
    max_tokens: 300,
    system:
      "Classify each job description into a short, normalized role category (2-5 words), e.g. \"Director of Strategy\" or \"Data/Analytics Leadership\". Return exactly one category per job description, in the same order given. Do not echo any text from the job descriptions themselves.",
    messages: [
      {
        role: "user",
        content: jds
          .map((jd, i) => `Job Description ${i + 1}:\n${jd.text}`)
          .join("\n\n"),
      },
    ],
    output_config: {
      format: {
        type: "json_schema",
        schema: {
          type: "object",
          properties: {
            categories: {
              type: "array",
              items: { type: "string" },
            },
          },
          required: ["categories"],
          additionalProperties: false,
        },
      },
    },
  });

  const block = response.content.find((b) => b.type === "text");
  const parsed = JSON.parse(block && block.type === "text" ? block.text : "{}") as {
    categories?: string[];
  };
  return parsed.categories?.slice(0, 3) ?? ["Unclassified", "Unclassified", "Unclassified"];
}

/**
 * Produces a short, non-identifying digest of the roadmap's conclusions —
 * NOT the full roadmap text — so patterns across users become visible over
 * time without retaining anyone's actual roadmap.
 */
async function extractSummaryFindings(fullRoadmapText: string): Promise<string[]> {
  const response = await anthropic.messages.create({
    model: MODELS.analytics,
    max_tokens: 400,
    system:
      "Read this career roadmap and extract 2 to 4 short, general findings about the KIND of gap identified (e.g. \"P&L ownership gap\", \"narrative/self-diagnosis mismatch\", \"timeline was aggressive relative to stated gaps\"). Do not include any names, companies, specific resume details, or verbatim text from the roadmap — these findings must not identify the person they came from.",
    messages: [{ role: "user", content: fullRoadmapText }],
    output_config: {
      format: {
        type: "json_schema",
        schema: {
          type: "object",
          properties: {
            findings: {
              type: "array",
              items: { type: "string" },
            },
          },
          required: ["findings"],
          additionalProperties: false,
        },
      },
    },
  });

  const block = response.content.find((b) => b.type === "text");
  const parsed = JSON.parse(block && block.type === "text" ? block.text : "{}") as {
    findings?: string[];
  };
  return parsed.findings ?? [];
}

/**
 * Called once, synchronously, at the end of the same request that generated
 * the roadmap. This is the ONLY function with access to resumeText / jds[].text
 * / fullRoadmapText — it never writes any of those three things to Supabase,
 * a log line, or a file. Only the short derived outputs below (role categories,
 * summary findings) are ever persisted. Failures here are caught by the caller
 * and must never surface to the client — the roadmap stream has already closed.
 */
export async function recordAnalyticsInBackground(input: {
  jds: [JobDescription, JobDescription, JobDescription];
  answers: Answers;
  fullRoadmapText: string;
  promptVersion: string;
  email: string | null;
}): Promise<void> {
  const [roleCategories, summaryFindings] = await Promise.all([
    extractRoleCategories(input.jds),
    extractSummaryFindings(input.fullRoadmapText),
  ]);

  const { error } = await getSupabase().from("runs").insert({
    email: input.email || null,
    role_categories: roleCategories,
    summary_findings: summaryFindings,
    prompt_version: input.promptVersion,
  });

  if (error) throw new Error(`Supabase insert failed: ${error.message}`);
}
