import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { Button } from "../components/ui/Button";
import { Tabs, type TabDef } from "../components/ui/Tabs";
import { useAuth } from "../hooks/useAuth";
import { hasPermission } from "../lib/permissions";
import type { Permission } from "../lib/permissions";
import type { SettingsSchema } from "../types";
import { MyCredentialsTab } from "./settings/MyCredentialsTab";
import { SchemaGroup, type StrategyOptions } from "./settings/SchemaGroup";
import { SETTINGS_SECTION_ORDER, buildSchemaTree, emptyGroup, humanize } from "./settings/schemaTree";
import { SecurityTab } from "./settings/SecurityTab";
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

// Renders a nested tab strip, but skips the tab chrome entirely when there's only one
// tab to show (e.g. a viewer's Broker tab has no Credentials sub-tab to switch to).
function NestedTabs({ tabs }: { tabs: TabDef[] }) {
  if (tabs.length === 1) return <>{tabs[0].content}</>;
  return <Tabs level="nested" tabs={tabs} />;
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
  const [strategyOptions, setStrategyOptions] = useState<StrategyOptions>({ buy: [], sell: [] });
  const [edited, setEdited] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState<Status | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api
      .settingsSchema()
      .then(setSchema)
      .catch((e) => setStatus({ text: (e as Error).message, tone: "error" }));
    api
      .strategies()
      .then((list) =>
        setStrategyOptions({
          buy: list.filter((s) => s.direction === "buy").map((s) => s.name),
          sell: list.filter((s) => s.direction === "sell").map((s) => s.name),
        }),
      )
      .catch(() => {});
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

  function schemaTab(name: string) {
    return schemaLoaded ? (
      <SchemaGroup
        node={tree[name] ?? emptyGroup()}
        edited={edited}
        onChange={onFieldChange}
        readOnly={!hasPermission(role, sectionPermission(name))}
        strategyOptions={strategyOptions}
      />
    ) : (
      <p className="py-6 text-center text-sm text-white/40">Loading…</p>
    );
  }

  // Broker: its own settings plus the platform credentials for it, nested together.
  const brokerTabs: TabDef[] = [{ id: "broker-settings", label: "Settings", content: schemaTab("broker") }];
  if (canSystem) {
    brokerTabs.push({ id: "credentials", label: "Credentials", content: <SystemCredentialsTab /> });
  }
  if (canCredentials) {
    brokerTabs.push({ id: "my-credentials", label: "My Credentials", content: <MyCredentialsTab /> });
  }

  // Fixed tab list — order and presence never change across renders (aside from the
  // role-gated sub-tabs, which depend only on `role`, resolved synchronously at mount),
  // so the tab bar never reshuffles or flickers while the schema loads.
  const tabs: TabDef[] = SETTINGS_SECTION_ORDER.map((name) =>
    name === "broker"
      ? { id: "broker", label: "Broker", content: <NestedTabs tabs={brokerTabs} /> }
      : { id: name, label: humanize(name), content: schemaTab(name) },
  );

  // Service: logging + git sync, grouped since both are infra-level, admin-only knobs.
  tabs.push({
    id: "service",
    label: "Service",
    content: (
      <NestedTabs
        tabs={[
          { id: "logging", label: "Logging", content: schemaTab("logger") },
          { id: "git-sync", label: "Git Sync", content: schemaTab("git_sync") },
        ]}
      />
    ),
  });

  tabs.push({ id: "security", label: "Security", content: <SecurityTab /> });

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

