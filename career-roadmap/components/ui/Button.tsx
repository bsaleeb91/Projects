import { ButtonHTMLAttributes } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary";
};

export function Button({ variant = "primary", className = "", ...props }: Props) {
  const base =
    "inline-flex items-center justify-center rounded-md px-5 py-2.5 text-[0.95rem] font-medium transition-colors motion-reduce:transition-none disabled:opacity-40 disabled:cursor-not-allowed";
  const variants = {
    primary: "bg-accent text-white hover:bg-accent/90",
    secondary:
      "bg-transparent text-ink border border-line hover:bg-paper-muted",
  };
  return <button className={`${base} ${variants[variant]} ${className}`} {...props} />;
}
