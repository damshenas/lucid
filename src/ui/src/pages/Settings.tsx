import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { SettingsSchema } from "../types";

// Fully schema-driven: the form is derived from GET /settings/schema. No hardcoded fields.
export function Settings() {
  const [schema, setSchema] = useState<SettingsSchema>({});
  const [edited, setEdited] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState<string | null>(null);

  useEffect(() => {
    api.settingsSchema().then(setSchema).catch((e) => setStatus((e as Error).message));
  }, []);

  function onChange(section: string, field: string, raw: string, type: string) {
    const key = `${section}.${field}`;
    let value: unknown = raw;
    if (type === "int") value = parseInt(raw, 10);
    else if (type === "float") value = parseFloat(raw);
    else if (type === "bool") value = raw === "true";
    setEdited((prev) => ({ ...prev, [key]: value }));
  }

  async function save() {
    try {
      await api.saveSettings(edited);
      setStatus("Saved.");
    } catch (e) {
      setStatus((e as Error).message);
    }
  }

  return (
    <div>
      <h2>Settings</h2>
      {Object.entries(schema).map(([section, fields]) => (
        <fieldset key={section} style={{ marginBottom: 12 }}>
          <legend>{section}</legend>
          {Object.entries(fields).map(([field, meta]) => {
            const key = `${section}.${field}`;
            const current = key in edited ? edited[key] : meta.value;
            return (
              <label key={field} style={{ display: "block", marginBottom: 4 }}>
                {field} ({meta.type}){" "}
                <input
                  defaultValue={String(current ?? "")}
                  onChange={(e) => onChange(section, field, e.target.value, meta.type)}
                />
              </label>
            );
          })}
        </fieldset>
      ))}
      <button onClick={save}>Save</button>
      {status && <p>{status}</p>}
    </div>
  );
}
