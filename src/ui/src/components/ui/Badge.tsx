import type { ReactNode } from "react";

type Tone = "violet" | "cyan" | "rose" | "neutral";

interface Props {
  children: ReactNode;
  tone?: Tone;
}

const TONE_CLASSES: Record<Tone, string> = {
  violet: "bg-violet/15 text-violet border-violet/30",
  cyan: "bg-cyan/15 text-cyan border-cyan/30",
  rose: "bg-rose/15 text-rose border-rose/30",
  neutral: "bg-white/10 text-white/70 border-white/10",
};

export function Badge({ children, tone = "neutral" }: Props) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium
        ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}
