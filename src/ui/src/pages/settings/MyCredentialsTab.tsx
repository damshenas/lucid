import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Toggle } from "../../components/ui/Toggle";
import type { CredentialCatalogItem } from "../../types";

interface Status {
  text: string;
  tone: "success" | "error";
}

/** Trader-only: own broker credentials, with a fallback to the admin-configured
 * system defaults via "use default credentials" (see modules/encryption/credentials.py). */
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

      <Card>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/40">
          My credentials
        </h3>
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
    </div>
  );
}
