import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { Button } from "../components/ui/Button";
import { Tabs, type TabDef } from "../components/ui/Tabs";
import { useAuth } from "../hooks/useAuth";
import { hasPermission } from "../lib/permissions";
import type { SettingsSchema } from "../types";
import { AccountTab } from "./settings/AccountTab";
import { MyCredentialsTab } from "./settings/MyCredentialsTab";
import { SchemaGroup } from "./settings/SchemaGroup";
import { buildSchemaTree, humanize } from "./settings/schemaTree";
import { SystemCredentialsTab } from "./settings/SystemCredentialsTab";

interface Status {
  text: string;
  tone: "success" | "error";
}

// The "System" and "Strategy" tabs are fully schema-driven from GET /settings/schema —
// no hardcoded fields, no hardcoded nesting. See pages/settings/schemaTree.ts.
export function Settings() {
  const { role } = useAuth();
  const canSystem = hasPermission(role, "edit_system_settings");
  const canStrategy = hasPermission(role, "edit_own_strategies");
  const canCredentials = hasPermission(role, "edit_own_credentials");

  const [schema, setSchema] = useState<SettingsSchema>({});
  const [edited, setEdited] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState<Status | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!canSystem && !canStrategy) return;
    api
      .settingsSchema()
      .then(setSchema)
      .catch((e) => setStatus({ text: (e as Error).message, tone: "error" }));
  }, [canSystem, canStrategy]);

  useEffect(() => {
    if (!status) return;
    const timer = setTimeout(() => setStatus(null), 4000);
    return () => clearTimeout(timer);
  }, [status]);

  const tree = useMemo(() => buildSchemaTree(schema), [schema]);

  function onFieldChange(key: string, raw: string, type: string) {
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
      setEdited({});
      setStatus({ text: "Saved.", tone: "success" });
    } catch (e) {
      setStatus({ text: (e as Error).message, tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  const tabs: TabDef[] = [];

  if (canSystem) {
    const systemRoots = Object.keys(tree).filter((name) => name !== "strategy");
    tabs.push({
      id: "system",
      label: "System",
      content: (
        <Tabs
          level="nested"
          tabs={[
            ...systemRoots.map((name) => ({
              id: name,
              label: humanize(name),
              content: <SchemaGroup node={tree[name]} edited={edited} onChange={onFieldChange} />,
            })),
            { id: "credentials", label: "Credentials", content: <SystemCredentialsTab /> },
          ]}
        />
      ),
    });
  }

  if (canStrategy) {
    tabs.push({
      id: "strategy",
      label: "Strategy",
      content: tree.strategy ? (
        <SchemaGroup node={tree.strategy} edited={edited} onChange={onFieldChange} />
      ) : (
        <p className="py-6 text-center text-sm text-white/40">Loading…</p>
      ),
    });
  }

  if (canCredentials) {
    tabs.push({ id: "my-credentials", label: "My Credentials", content: <MyCredentialsTab /> });
  }

  tabs.push({ id: "account", label: "Account", content: <AccountTab /> });

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

      <Tabs tabs={tabs} />

      {(canSystem || canStrategy) && (
        <Button onClick={save} disabled={saving || Object.keys(edited).length === 0} className="w-full">
          {saving ? "Saving…" : "Save changes"}
        </Button>
      )}
    </div>
  );
}
