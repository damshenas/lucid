import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  icon?: ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-gradient-to-r from-violet to-cyan text-white shadow-lg shadow-violet/20 hover:brightness-110 focus-visible:glow-violet",
  secondary:
    "bg-elevated text-white/90 border border-white/10 hover:bg-white/10 focus-visible:glow-cyan",
  ghost: "bg-transparent text-white/70 hover:text-white hover:bg-white/5",
};

export function Button({ variant = "primary", icon, className = "", children, ...rest }: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-2xl px-4 py-2.5 text-sm font-medium
        transition-all duration-200 ease-out active:scale-95 disabled:opacity-50 disabled:pointer-events-none
        outline-none focus-visible:ring-2 focus-visible:ring-violet/60
        ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      {icon}
      {children}
    </button>
  );
}
