import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { Button } from "../components/ui/Button";
import { Tabs, type TabDef } from "../components/ui/Tabs";
import { useAuth } from "../hooks/useAuth";
import { hasPermission } from "../lib/permissions";
import type { Permission } from "../lib/permissions";
import type { SettingsSchema } from "../types";
import { AccountTab } from "./settings/AccountTab";
import { MyCredentialsTab } from "./settings/MyCredentialsTab";
import { SchemaGroup } from "./settings/SchemaGroup";
import { SETTINGS_SECTION_ORDER, buildSchemaTree, emptyGroup, humanize } from "./settings/schemaTree";
import { SystemCredentialsTab } from "./settings/SystemCredentialsTab";

interface Status {
  text: string;
  tone: "success" | "error";
}

// Mirrors required_permission_for_key() in src/modules/configs/__init__.py: only the
// "strategy" section is trader-editable, everything else is an admin-only "system
// default". Used to disable (not hide) sections the current role can't write to.
function sectionPermission(name: string): Permission {
  return name === "strategy" ? "edit_own_strategies" : "edit_system_settings";
}

// Every schema section is fetched and shown to every authenticated user — the backend
// GET /settings/schema endpoint itself has no permission gate, and hiding sections a
// role merely can't edit is confusing ("where did my settings go?"). Sections the role
// can't write to are rendered read-only instead of hidden.
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

  const tree = useMemo(() => buildSchemaTree(schema), [schema]);
  const schemaLoaded = Object.keys(schema).length > 0;

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

  // Fixed tab list — order and presence never change across renders (aside from the
  // role-gated Credentials tabs, which depend only on `role`, resolved synchronously
  // at mount), so the tab bar never reshuffles or flickers while the schema loads.
  const tabs: TabDef[] = SETTINGS_SECTION_ORDER.map((name) => ({
    id: name,
    label: humanize(name),
    content: schemaLoaded ? (
      <SchemaGroup
        node={tree[name] ?? emptyGroup()}
        edited={edited}
        onChange={onFieldChange}
        readOnly={!hasPermission(role, sectionPermission(name))}
      />
    ) : (
      <p className="py-6 text-center text-sm text-white/40">Loading…</p>
    ),
  }));

  if (canSystem) {
    tabs.push({ id: "credentials", label: "Credentials", content: <SystemCredentialsTab /> });
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
