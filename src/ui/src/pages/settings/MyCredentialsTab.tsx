import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Card } from "../../components/ui/Card";
import { Toggle } from "../../components/ui/Toggle";
import type { CredentialCatalogItem } from "../../types";
import { CredentialFields } from "./CredentialFields";

interface Status {
  text: string;
  tone: "success" | "error";
}

/** Trader-only: own broker credentials, with a fallback to the admin-configured
 * system defaults via "use default credentials" (see modules/encryption/credentials.py).
 * Grouped by platform (Trading212, and whatever's added later) so every platform
 * lives in this one tab instead of getting its own. */
export function MyCredentialsTab() {
  const [useDefault, setUseDefault] = useState(false);
  const [items, setItems] = useState<CredentialCatalogItem[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<Status | null>(null);
  const [savingKey, setSavingKey] = useState<string | null>(null);
  const [togglingDefault, setTogglingDefault] = useState(false);

  function refresh() {
    api
      .myCredentials()
      .then((data) => {
        setUseDefault(data.use_default_credentials);
        setItems(data.credentials);
      })
      .catch((e) => setStatus({ text: (e as Error).message, tone: "error" }));
  }

  useEffect(refresh, []);

  async function save(key: string) {
    const value = drafts[key];
    if (!value) return;
    setSavingKey(key);
    setStatus(null);
    try {
      await api.setMyCredential(key, value);
      setDrafts((prev) => ({ ...prev, [key]: "" }));
      setStatus({ text: "Saved.", tone: "success" });
      refresh();
    } catch (e) {
      setStatus({ text: (e as Error).message, tone: "error" });
    } finally {
      setSavingKey(null);
    }
  }

  async function toggleUseDefault(checked: boolean) {
    setTogglingDefault(true);
    try {
      await api.setUseDefaultCredentials(checked);
      setUseDefault(checked);
    } catch (e) {
      setStatus({ text: (e as Error).message, tone: "error" });
    } finally {
      setTogglingDefault(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-white/90">Use system default credentials</p>
            <p className="text-sm text-white/50">
              When enabled, your own credentials below are ignored in favor of the
              admin-configured platform defaults.
            </p>
          </div>
          <Toggle
            checked={useDefault}
            onChange={toggleUseDefault}
            disabled={togglingDefault}
            label="Use system default credentials"
          />
        </div>
      </Card>

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

