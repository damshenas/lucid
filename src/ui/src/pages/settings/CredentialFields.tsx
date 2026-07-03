import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import type { CredentialCatalogItem } from "../../types";

interface Props {
  items: CredentialCatalogItem[];
  drafts: Record<string, string>;
  savingKey: string | null;
  onDraftChange: (key: string, value: string) => void;
  onSave: (key: string) => void;
  /** Restrict to one platform's fields and skip the platform-name heading — used when
   * this is already embedded inside that platform's own tab (e.g. Broker > Trading212),
   * so repeating the platform name would be redundant. */
  platform?: string;
}

function FieldRow({
  item,
  draft,
  saving,
  onDraftChange,
  onSave,
}: {
  item: CredentialCatalogItem;
  draft: string;
  saving: boolean;
  onDraftChange: (value: string) => void;
  onSave: () => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="block min-w-[14rem] flex-1">
        <span className="mb-1 flex items-center gap-2 text-sm text-white/80">
          {item.label}
          <Badge tone={item.configured ? "cyan" : "neutral"}>
            {item.configured ? "configured" : "not set"}
          </Badge>
        </span>
        <input
          type={item.secret ? "password" : "text"}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          placeholder={item.configured ? "••••••••" : `Set ${item.label}`}
          className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
        />
      </label>
      <Button variant="secondary" disabled={!draft || saving} onClick={onSave}>
        {saving ? "Saving…" : "Save"}
      </Button>
    </div>
  );
}

/** Groups the credential catalog by platform so each platform (Trading212, and
 * whatever else gets added later) gets its own section — either filtered down to a
 * single platform (see `platform` prop) when embedded in that platform's own tab, or
 * grouped with a heading per platform when shown standalone. */
export function CredentialFields({ items, drafts, savingKey, onDraftChange, onSave, platform }: Props) {
  const filtered = platform ? items.filter((i) => i.platform === platform) : items;

  if (filtered.length === 0) {
    return <p className="py-6 text-center text-sm text-white/40">No platform credentials available.</p>;
  }

  if (platform) {
    return (
      <div className="space-y-3">
        {filtered.map((item) => (
          <FieldRow
            key={item.key}
            item={item}
            draft={drafts[item.key] ?? ""}
            saving={savingKey === item.key}
            onDraftChange={(value) => onDraftChange(item.key, value)}
            onSave={() => onSave(item.key)}
          />
        ))}
      </div>
    );
  }

  const byPlatform = new Map<string, CredentialCatalogItem[]>();
  for (const item of filtered) {
    const list = byPlatform.get(item.platform) ?? [];
    list.push(item);
    byPlatform.set(item.platform, list);
  }

  return (
    <div className="space-y-4">
      {[...byPlatform.entries()].map(([platformName, platformItems]) => (
        <Card key={platformName}>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/40">
            {platformName}
          </h3>
          <div className="space-y-3">
            {platformItems.map((item) => (
              <FieldRow
                key={item.key}
                item={item}
                draft={drafts[item.key] ?? ""}
                saving={savingKey === item.key}
                onDraftChange={(value) => onDraftChange(item.key, value)}
                onSave={() => onSave(item.key)}
              />
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
