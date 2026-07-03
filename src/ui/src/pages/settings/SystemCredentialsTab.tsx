import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { CredentialCatalogItem } from "../../types";
import { CredentialFields } from "./CredentialFields";

interface Status {
  text: string;
  tone: "success" | "error";
}

/** Admin-only: manages global (system-default) platform credentials, e.g. the broker
 * API key used when a trader has "use default credentials" enabled. Values are
 * write-only — the server never returns plaintext or ciphertext, only a
 * "configured" flag. Grouped by platform (Trading212, and whatever's added later) so
 * every platform lives in this one tab instead of getting its own. */
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
    <div className="space-y-3">
      <p className="text-sm text-white/50">
        System-level defaults used when a trader has "use default credentials" enabled.
        Values are write-only and never displayed once saved.
      </p>
      {status && (
        <p
          className={`rounded-xl border px-3 py-2 text-sm ${
            status.tone === "success"
              ? "border-cyan/30 bg-cyan/10 text-cyan"
              : "border-rose/30 bg-rose/10 text-rose"
          }`}
        >
          {status.text}
        </p>
      )}
      <CredentialFields
        items={items}
        drafts={drafts}
        savingKey={savingKey}
        onDraftChange={(key, value) => setDrafts((prev) => ({ ...prev, [key]: value }))}
        onSave={save}
      />
    </div>
  );
}

