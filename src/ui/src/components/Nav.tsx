interface Props {
  current: string;
  onNavigate: (view: string) => void;
  onLogout: () => void;
}

const ITEMS = ["dashboard", "strategies", "settings"];

export function Nav({ current, onNavigate, onLogout }: Props) {
  return (
    <nav style={{ display: "flex", gap: 12, borderBottom: "1px solid #ccc", padding: 8 }}>
      <strong style={{ marginRight: "auto" }}>Lucid</strong>
      {ITEMS.map((item) => (
        <button
          key={item}
          onClick={() => onNavigate(item)}
          style={{ fontWeight: current === item ? "bold" : "normal" }}
        >
          {item}
        </button>
      ))}
      <button onClick={onLogout}>logout</button>
    </nav>
  );
}
