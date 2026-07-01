import { useEffect, useState } from "react";
import { api } from "../api/client";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { Toggle } from "../components/ui/Toggle";
import type { SettingsSchema } from "../types";

interface Status {
  text: string;
  tone: "success" | "error";
}

// Fully schema-driven: the form is derived from GET /settings/schema. No hardcoded fields.
export function Settings() {
  const [schema, setSchema] = useState<SettingsSchema>({});
  const [edited, setEdited] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState<Status | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .settingsSchema()
      .then(setSchema)
      .catch((e) => setStatus({ text: (e as Error).message, tone: "error" }));
  }, []);

  useEffect(() => {
    if (!status) return;
    const timer = setTimeout(() => setStatus(null), 4000);
    return () => clearTimeout(timer);
  }, [status]);

  function onChange(section: string, field: string, raw: string, type: string) {
    const key = `${section}.${field}`;
    let value: unknown = raw;
    if (type === "int") value = parseInt(raw, 10);
    else if (type === "float") value = parseFloat(raw);
    else if (type === "bool") value = raw === "true";
    setEdited((prev) => ({ ...prev, [key]: value }));
  }

  async function save() {
    setSaving(true);
    try {
      await api.saveSettings(edited);
      setStatus({ text: "Saved.", tone: "success" });
    } catch (e) {
      setStatus({ text: (e as Error).message, tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="animate-fade-in-up space-y-4">
      <h2 className="text-xl font-semibold tracking-tight">Settings</h2>

      {status && (
        <div
          className={`rounded-xl border px-3 py-2 text-sm ${
            status.tone === "success"
              ? "border-cyan/30 bg-cyan/10 text-cyan"
              : "border-rose/30 bg-rose/10 text-rose"
          }`}
        >
          {status.text}
        </div>
      )}

      {Object.entries(schema).map(([section, fields]) => (
        <Card key={section}>
          <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/40">
            {section}
          </h3>
          <div className="space-y-3">
            {Object.entries(fields).map(([field, meta]) => {
              const key = `${section}.${field}`;
              const current = key in edited ? edited[key] : meta.value;
              if (meta.type === "bool") {
                return (
                  <div key={field} className="flex items-center justify-between gap-3">
                    <span className="text-sm text-white/80">{field}</span>
                    <Toggle
                      checked={Boolean(current)}
                      onChange={(checked) =>
                        onChange(section, field, String(checked), "bool")
                      }
                      label={field}
                    />
                  </div>
                );
              }
              return (
                <label key={field} className="block">
                  <span className="mb-1 block text-sm text-white/80">{field}</span>
                  <input
                    defaultValue={String(current ?? "")}
                    type={meta.type === "int" || meta.type === "float" ? "number" : "text"}
                    onChange={(e) => onChange(section, field, e.target.value, meta.type)}
                    className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
                  />
                </label>
              );
            })}
          </div>
        </Card>
      ))}

      <Button onClick={save} disabled={saving} className="w-full">
        {saving ? "Saving…" : "Save changes"}
      </Button>
    </div>
  );
}
