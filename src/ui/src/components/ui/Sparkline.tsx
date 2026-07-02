interface Props {
  values: number[];
  className?: string;
  stroke?: string;
}

/** Minimal inline SVG trend line — no charting library needed for a single series. */
export function Sparkline({ values, className = "", stroke = "#06b6d4" }: Props) {
  if (values.length < 2) return null;

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const step = 100 / (values.length - 1);
  const points = values
    .map((v, i) => `${(i * step).toFixed(2)},${(29 - ((v - min) / range) * 28).toFixed(2)}`)
    .join(" ");

  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className={className}>
      <polyline
        points={points}
        fill="none"
        stroke={stroke}
        strokeWidth={1.5}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
