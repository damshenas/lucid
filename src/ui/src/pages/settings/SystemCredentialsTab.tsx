import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import type { CredentialCatalogItem } from "../../types";

interface Status {
  text: string;
  tone: "success" | "error";
}

/** Admin-only: manages global (system-default) platform credentials, e.g. the broker
 * API key used when a trader has "use default credentials" enabled. Values are
 * write-only — the server never returns plaintext or ciphertext, only a
 * "configured" flag. */
export function SystemCredentialsTab() {
  const [items, setItems] = useState<CredentialCatalogItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<Status | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);

  function refresh() {
    api.systemCredentials().then(setItems).catch((e) => setStatus({ text: (e as Error).message, tone: "error" }));
  }

  useEffect(refresh, []);

  async function save(key: string) {
    const value = drafts[key];
    if (!value) return;
    setSavingKey(key);
    setStatus(null);
    try {
      await api.setSystemCredential(key, value);
      setDrafts((prev) => ({ ...prev, [key]: "" }));
      setStatus({ text: "Saved.", tone: "success" });
      refresh();
    } catch (e) {
      setStatus({ text: (e as Error).message, tone: "error" });
    } finally {
      setSavingKey(null);
    }
  }

  return (
    <Card>
      <h3 className="mb-1 text-sm font-semibold uppercase tracking-wide text-white/40">
        Platform credentials
      </h3>
      <p className="mb-4 text-sm text-white/50">
        System-level defaults used when a trader has "use default credentials" enabled.
        Values are write-only and never displayed once saved.
      </p>
      {status && (
        <p
          className={`mb-3 rounded-xl border px-3 py-2 text-sm ${
            status.tone === "success"
              ? "border-cyan/30 bg-cyan/10 text-cyan"
              : "border-rose/30 bg-rose/10 text-rose"
          }`}
        >
          {status.text}
        </p>
      )}
      <div className="space-y-3">
        {items.map((item) => (
          <div key={item.key} className="flex flex-wrap items-end gap-3">
            <label className="block flex-1 min-w-[14rem]">
              <span className="mb-1 flex items-center gap-2 text-sm text-white/80">
                {item.label}
                <Badge tone={item.configured ? "cyan" : "neutral"}>
                  {item.configured ? "configured" : "not set"}
                </Badge>
              </span>
              <input
                type={item.secret ? "password" : "text"}
                value={drafts[item.key] ?? ""}
                onChange={(e) => setDrafts((prev) => ({ ...prev, [item.key]: e.target.value }))}
                placeholder={item.configured ? "••••••••" : `Set ${item.label}`}
                className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
              />
            </label>
            <Button
              variant="secondary"
              disabled={!drafts[item.key] || savingKey === item.key}
              onClick={() => save(item.key)}
            >
              {savingKey === item.key ? "Saving…" : "Save"}
            </Button>
          </div>
        ))}
      </div>
    </Card>
  );
}
