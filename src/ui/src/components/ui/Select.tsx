import type { ReactNode, SelectHTMLAttributes } from "react";
import { ChevronDown } from "lucide-react";

interface Props extends SelectHTMLAttributes<HTMLSelectElement> {
  children: ReactNode;
}

/** Styled <select> — the native control's default appearance (browser-drawn arrow,
 * light-themed popup chrome) looks broken against the dark glass UI, so we suppress
 * it and draw our own chevron. */
export function Select({ className = "", children, ...rest }: Props) {
  return (
    <div className="relative">
      <select
        {...rest}
        className={`w-full appearance-none rounded-xl border border-white/10 bg-elevated px-3.5 py-2 pr-9 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet disabled:cursor-not-allowed disabled:opacity-50 ${className}`}
      >
        {children}
      </select>
      <ChevronDown
        size={16}
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-white/40"
      />
    </div>
  );
}
