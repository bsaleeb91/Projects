import { TextareaHTMLAttributes } from "react";

type Props = TextareaHTMLAttributes<HTMLTextAreaElement> & {
  label: string;
  hint?: string;
  error?: string;
};

export function TextArea({ label, hint, error, className = "", id, ...props }: Props) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-sm font-medium text-ink">
        {label}
      </label>
      {hint && <p className="text-meta text-ink-muted">{hint}</p>}
      <textarea
        id={id}
        className={`w-full rounded-md border border-line bg-paper px-3 py-2.5 text-[0.95rem] leading-relaxed text-ink outline-none placeholder:text-ink-muted ${className}`}
        {...props}
      />
      {error && <p className="text-meta text-red-600">{error}</p>}
    </div>
  );
}
