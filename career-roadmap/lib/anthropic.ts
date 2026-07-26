import Anthropic from "@anthropic-ai/sdk";

/** Single shared client — reads ANTHROPIC_API_KEY from the environment. Server-only. */
export const anthropic = new Anthropic();

export const MODELS = {
  /** Long-form roadmap generation — cost-sensitive, high-quality prose. */
  roadmap: "claude-sonnet-5",
  /** Cheap classification/summarization for analytics extraction only. */
  analytics: "claude-haiku-4-5",
} as const;
