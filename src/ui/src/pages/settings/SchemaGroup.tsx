import { Card } from "../../components/ui/Card";
import { Tabs } from "../../components/ui/Tabs";
import { Toggle } from "../../components/ui/Toggle";
import type { SchemaField } from "../../types";
import { type GroupNode, humanize } from "./schemaTree";

interface FieldProps {
  fieldKey: string;
  meta: SchemaField;
  current: unknown;
  onChange: (key: string, raw: string, type: string) => void;
}

function Field({ fieldKey, meta, current, onChange }: FieldProps) {
  const label = humanize(fieldKey.split(".").pop() ?? fieldKey);
  if (meta.type === "bool") {
    return (
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-white/80">{label}</span>
        <Toggle
          checked={Boolean(current)}
          onChange={(checked) => onChange(fieldKey, String(checked), "bool")}
          label={label}
        />
      </div>
    );
  }
  return (
    <label className="block">
      <span className="mb-1 block text-sm text-white/80">{label}</span>
      <input
        defaultValue={String(current ?? "")}
        type={meta.type === "int" || meta.type === "float" ? "number" : "text"}
        onChange={(e) => onChange(fieldKey, e.target.value, meta.type)}
        className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
      />
    </label>
  );
}

interface Props {
  node: GroupNode;
  edited: Record<string, unknown>;
  onChange: (key: string, raw: string, type: string) => void;
}

/** Renders one schema tree node: its own fields as a form, plus any nested groups as
 * nested tabs (recursively) — fully generic, driven by whatever the backend reports. */
export function SchemaGroup({ node, edited, onChange }: Props) {
  const groupEntries = Object.entries(node.groups);

  return (
    <div className="space-y-4">
      {node.fields.length > 0 && (
        <Card>
          <div className="space-y-3">
            {node.fields.map(({ key, field }) => (
              <Field
                key={key}
                fieldKey={key}
                meta={field}
                current={key in edited ? edited[key] : field.value}
                onChange={onChange}
              />
            ))}
          </div>
        </Card>
      )}
      {groupEntries.length > 0 && (
        <Tabs
          level="nested"
          tabs={groupEntries.map(([name, sub]) => ({
            id: name,
            label: humanize(name),
            content: <SchemaGroup node={sub} edited={edited} onChange={onChange} />,
          }))}
        />
      )}
      {node.fields.length === 0 && groupEntries.length === 0 && (
        <p className="py-6 text-center text-sm text-white/40">Nothing to configure here.</p>
      )}
    </div>
  );
}
