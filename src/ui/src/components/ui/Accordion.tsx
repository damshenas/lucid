import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";

interface Props {
  title: string;
  children: ReactNode;
  defaultOpen?: boolean;
}

/** Native <details>/<summary> accordion — no JS state needed, keyboard accessible by default. */
export function Accordion({ title, children, defaultOpen = true }: Props) {
  return (
    <details open={defaultOpen} className="group">
      <summary className="mb-3 flex cursor-pointer list-none items-center justify-between text-sm font-semibold uppercase tracking-wide text-white/40 [&::-webkit-details-marker]:hidden">
        <span>{title}</span>
        <ChevronDown
          size={16}
          className="text-white/30 transition-transform duration-200 group-open:rotate-180"
        />
      </summary>
      <div className="space-y-3">{children}</div>
    </details>
  );
}
