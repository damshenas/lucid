import type { HTMLAttributes, ReactNode } from "react";

interface Props extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  glow?: "violet" | "cyan" | "rose" | "none";
}

const GLOW_CLASSES: Record<NonNullable<Props["glow"]>, string> = {
  violet: "glow-violet",
  cyan: "glow-cyan",
  rose: "glow-rose",
  none: "",
};

export function Card({ children, glow = "none", className = "", ...rest }: Props) {
  return (
    <div
      className={`glass rounded-2xl p-4 sm:p-5 ${GLOW_CLASSES[glow]} ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}
