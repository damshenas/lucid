import { useState } from "react";
import type { ReactNode } from "react";

export interface TabDef {
  id: string;
  label: string;
  content: ReactNode;
}

interface Props {
  tabs: TabDef[];
  /** Visual weight — nested tabs render smaller/quieter than top-level ones. */
  level?: "primary" | "nested";
}

/** Simple controlled-internally tab strip. Supports nesting by rendering another
 * <Tabs> inside a tab's `content`. */
export function Tabs({ tabs, level = "primary" }: Props) {
  const [active, setActive] = useState(tabs[0]?.id);
  if (tabs.length === 0) return null;
  const current = tabs.find((t) => t.id === active) ?? tabs[0];

  return (
    <div className={level === "primary" ? "space-y-4" : "space-y-3"}>
      <div
        role="tablist"
        className={`flex flex-wrap gap-1 ${
          level === "primary"
            ? "border-b border-white/10 pb-0"
            : "rounded-xl border border-white/10 bg-white/5 p-1"
        }`}
      >
        {tabs.map((tab) => {
          const isActive = tab.id === current.id;
          return (
            <button
              key={tab.id}
              role="tab"
              type="button"
              aria-selected={isActive}
              onClick={() => setActive(tab.id)}
              className={
                level === "primary"
                  ? `-mb-px border-b-2 px-3.5 py-2.5 text-sm font-medium transition-colors duration-150
                    ${
                      isActive
                        ? "border-violet text-white"
                        : "border-transparent text-white/50 hover:text-white/80"
                    }`
                  : `rounded-lg px-3 py-1.5 text-xs font-medium transition-colors duration-150
                    ${
                      isActive
                        ? "bg-white/10 text-white"
                        : "text-white/50 hover:text-white/80"
                    }`
              }
            >
              {tab.label}
            </button>
          );
        })}
      </div>
      <div className="animate-fade-in-up">{current.content}</div>
    </div>
  );
}
