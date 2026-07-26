const STEPS = ["Upload", "Questions", "Roadmap"] as const;

export function ProgressDots({ activeIndex }: { activeIndex: number }) {
  return (
    <ol className="flex items-center gap-3" aria-label="Progress">
      {STEPS.map((label, i) => (
        <li key={label} className="flex items-center gap-2">
          <span
            aria-current={i === activeIndex ? "step" : undefined}
            className={`h-2 w-2 rounded-full transition-colors motion-reduce:transition-none ${
              i <= activeIndex ? "bg-accent" : "bg-line"
            }`}
          />
          <span
            className={`text-meta ${
              i === activeIndex ? "text-ink font-medium" : "text-ink-muted"
            }`}
          >
            {label}
          </span>
          {i < STEPS.length - 1 && <span className="text-ink-muted">—</span>}
        </li>
      ))}
    </ol>
  );
}
