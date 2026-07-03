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
}

/** Groups the credential catalog by platform so each platform (Trading212, and
 * whatever else gets added later) gets its own titled section within a single
 * Credentials tab, rather than a new tab per platform. */
export function CredentialFields({ items, drafts, savingKey, onDraftChange, onSave }: Props) {
  const byPlatform = new Map<string, CredentialCatalogItem[]>();
  for (const item of items) {
    const list = byPlatform.get(item.platform) ?? [];
    list.push(item);
    byPlatform.set(item.platform, list);
  }

  if (items.length === 0) {
    return <p className="py-6 text-center text-sm text-white/40">No platform credentials available.</p>;
  }

  return (
    <div className="space-y-4">
      {[...byPlatform.entries()].map(([platform, platformItems]) => (
        <Card key={platform}>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/40">
            {platform}
          </h3>
          <div className="space-y-3">
            {platformItems.map((item) => (
              <div key={item.key} className="flex flex-wrap items-end gap-3">
                <label className="block min-w-[14rem] flex-1">
                  <span className="mb-1 flex items-center gap-2 text-sm text-white/80">
                    {item.label}
                    <Badge tone={item.configured ? "cyan" : "neutral"}>
                      {item.configured ? "configured" : "not set"}
                    </Badge>
                  </span>
                  <input
                    type={item.secret ? "password" : "text"}
                    value={drafts[item.key] ?? ""}
                    onChange={(e) => onDraftChange(item.key, e.target.value)}
                    placeholder={item.configured ? "••••••••" : `Set ${item.label}`}
                    className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
                  />
                </label>
                <Button
                  variant="secondary"
                  disabled={!drafts[item.key] || savingKey === item.key}
                  onClick={() => onSave(item.key)}
                >
                  {savingKey === item.key ? "Saving…" : "Save"}
                </Button>
              </div>
            ))}
          </div>
        </Card>
      ))}
    </div>
  );
}
