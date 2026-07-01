import type { ButtonHTMLAttributes, ReactNode } from "react";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon: ReactNode;
  label: string;
}

export function IconButton({ icon, label, className = "", ...rest }: Props) {
  return (
    <button
      aria-label={label}
      title={label}
      className={`inline-flex h-10 w-10 items-center justify-center rounded-xl text-white/70
        transition-all duration-200 hover:bg-white/10 hover:text-white active:scale-90
        outline-none focus-visible:ring-2 focus-visible:ring-violet/60 ${className}`}
      {...rest}
    >
      {icon}
    </button>
  );
}
