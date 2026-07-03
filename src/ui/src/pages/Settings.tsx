import { useEffect, useMemo, useState } from "react";
import { api } from "../api/client";
import { Button } from "../components/ui/Button";
import { Tabs, type TabDef } from "../components/ui/Tabs";
import { useAuth } from "../hooks/useAuth";
import { hasPermission } from "../lib/permissions";
import type { Role } from "../lib/permissions";
import type { SettingsSchema, Strategy } from "../types";
import { BrokerPlatformPanel } from "./settings/BrokerPlatformPanel";
import { SchemaGroup } from "./settings/SchemaGroup";
import { BROKER_PLATFORMS, SETTINGS_SECTION_ORDER, buildSchemaTree, emptyGroup, humanize } from "./settings/schemaTree";
import { SecurityTab } from "./settings/SecurityTab";
import { StrategyTab } from "./settings/StrategyTab";

interface Status {
  text: string;
  tone: "success" | "error";
}

// Mirrors can_write_key() in src/modules/configs/__init__.py: admin manages "system
// defaults" for every section (written globally); a trader may *additionally*
// override their own personal strategy.* choice. Used to disable (not hide) sections
// the current role can't write to.
function canWriteSection(role: Role | null, name: string): boolean {
  if (hasPermission(role, "edit_system_settings")) return true;
  return name === "strategy" && hasPermission(role, "edit_own_strategies");
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
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [strategiesLoaded, setStrategiesLoaded] = useState(false);
  const [edited, setEdited] = useState<Record<string, unknown>>({});
  const [status, setStatus] = useState<Status | null>(null);
  const [saving, setSaving] = useState(false);

  function refreshStrategies() {
    return api
      .strategies()
      .then(setStrategies)
      .catch((e) => setStatus({ text: (e as Error).message, tone: "error" }))
      .finally(() => setStrategiesLoaded(true));
  }

  useEffect(() => {
    api
      .settingsSchema()
      .then(setSchema)
      .catch((e) => setStatus({ text: (e as Error).message, tone: "error" }));
    // Every discovered strategy (active or not) — lets the Strategy tab show a
    // sub-tab per available strategy, not only whichever one is already active.
    refreshStrategies();
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
        readOnly={!canWriteSection(role, name)}
      />
    ) : (
      <p className="py-6 text-center text-sm text-white/40">Loading…</p>
    );
  }

  async function rescanStrategies() {
    try {
      await api.scanStrategies();
    } catch (e) {
      setStatus({ text: (e as Error).message, tone: "error" });
      return;
    }
    await refreshStrategies();
  }

  // Broker: one nested tab per platform, each showing whether it's active, paper
  // mode, and that platform's own credentials all together (not split across
  // separate "Settings"/"Credentials" sub-tabs).
  const brokerTabs: TabDef[] = BROKER_PLATFORMS.map((platform) => ({
    id: platform.id,
    label: platform.label,
    content: schemaLoaded ? (
      <BrokerPlatformPanel
        platform={platform}
        brokerNode={tree.broker ?? emptyGroup()}
        edited={edited}
        onChange={onFieldChange}
        readOnly={!canWriteSection(role, "broker")}
        canSystem={canSystem}
        canCredentials={canCredentials}
      />
    ) : (
      <p className="py-6 text-center text-sm text-white/40">Loading…</p>
    ),
  }));

  // Fixed tab list — order and presence never change across renders (aside from the
  // role-gated sub-tabs, which depend only on `role`, resolved synchronously at mount),
  // so the tab bar never reshuffles or flickers while the schema loads.
  const tabs: TabDef[] = SETTINGS_SECTION_ORDER.map((name) => {
    if (name === "broker") {
      return { id: "broker", label: "Broker", content: <Tabs level="nested" tabs={brokerTabs} /> };
    }
    if (name === "strategy") {
      return {
        id: "strategy",
        label: "Strategy",
        content: (
          <StrategyTab
            strategyNode={tree.strategy ?? emptyGroup()}
            strategies={strategies}
            strategiesLoaded={strategiesLoaded}
            onRescan={rescanStrategies}
            edited={edited}
            onChange={onFieldChange}
            readOnly={!canWriteSection(role, "strategy")}
          />
        ),
      };
    }
    return { id: name, label: humanize(name), content: schemaTab(name) };
  });

  // Service: logging + git sync, grouped since both are infra-level, admin-only knobs.
  tabs.push({
    id: "service",
    label: "Service",
    content: (
      <Tabs
        level="nested"
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

