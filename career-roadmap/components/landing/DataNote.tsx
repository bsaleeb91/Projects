import { DATA_HANDLING_NOTE } from "@/lib/content/landing-copy";

export function DataNote({ className = "" }: { className?: string }) {
  return (
    <p className={`text-meta text-ink-muted ${className}`}>{DATA_HANDLING_NOTE}</p>
  );
}
