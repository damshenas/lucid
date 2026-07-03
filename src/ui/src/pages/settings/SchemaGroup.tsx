import { Card } from "../../components/ui/Card";
import { Select } from "../../components/ui/Select";
import { Tabs } from "../../components/ui/Tabs";
import { Toggle } from "../../components/ui/Toggle";
import type { SchemaField } from "../../types";
import { type GroupNode, humanize } from "./schemaTree";

/** Leaf field name -> strategy direction, for fields that should render as a picker
 * over the actually-discovered strategies rather than a free-text box (M10). */
const STRATEGY_SELECT_FIELDS: Record<string, "buy" | "sell"> = {
  active_buy_strategy: "buy",
  active_sell_strategy: "sell",
};

export interface StrategyOptions {
  buy: string[];
  sell: string[];
}

interface FieldProps {
  fieldKey: string;
  meta: SchemaField;
  current: unknown;
  readOnly: boolean;
  strategyOptions?: StrategyOptions;
  onChange: (key: string, raw: string, type: string) => void;
}

function Field({ fieldKey, meta, current, readOnly, strategyOptions, onChange }: FieldProps) {
  const label = humanize(fieldKey.split(".").pop() ?? fieldKey);

  if (meta.type === "bool") {
    return (
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm text-white/80">{label}</span>
        <Toggle
          checked={Boolean(current)}
          onChange={(checked) => onChange(fieldKey, String(checked), "bool")}
          disabled={readOnly}
          label={label}
        />
      </div>
    );
  }

  const leaf = fieldKey.split(".").pop() ?? fieldKey;
  const direction = STRATEGY_SELECT_FIELDS[leaf];
  if (direction && strategyOptions) {
    const options = strategyOptions[direction];
    return (
      <label className="block">
        <span className="mb-1 block text-sm text-white/80">{label}</span>
        <Select
          value={String(current ?? "")}
          onChange={(e) => onChange(fieldKey, e.target.value, meta.type)}
          disabled={readOnly}
        >
          <option value="" className="bg-surface">
            — none —
          </option>
          {options.map((name) => (
            <option key={name} value={name} className="bg-surface">
              {name}
            </option>
          ))}
        </Select>
      </label>
    );
  }

  return (
    <label className="block">
      <span className="mb-1 block text-sm text-white/80">{label}</span>
      <input
        defaultValue={String(current ?? "")}
        type={meta.type === "int" || meta.type === "float" ? "number" : "text"}
        onChange={(e) => onChange(fieldKey, e.target.value, meta.type)}
        disabled={readOnly}
        className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet disabled:cursor-not-allowed disabled:opacity-50"
      />
    </label>
  );
}

interface Props {
  node: GroupNode;
  edited: Record<string, unknown>;
  onChange: (key: string, raw: string, type: string) => void;
  /** True when the current user lacks write permission for this section — fields are
   * still shown (parity with the pre-restructure page, which showed everything to
   * everyone) but disabled instead of hidden. */
  readOnly?: boolean;
  /** Discovered strategy names by direction, used for the active-strategy pickers. */
  strategyOptions?: StrategyOptions;
}

/** Renders one schema tree node: its own fields as a form, plus any nested groups as
 * nested tabs (recursively) — fully generic, driven by whatever the backend reports. */
export function SchemaGroup({ node, edited, onChange, readOnly = false, strategyOptions }: Props) {
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
                readOnly={readOnly}
                strategyOptions={strategyOptions}
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
            content: (
              <SchemaGroup
                node={sub}
                edited={edited}
                onChange={onChange}
                readOnly={readOnly}
                strategyOptions={strategyOptions}
              />
            ),
          }))}
        />
      )}
      {node.fields.length === 0 && groupEntries.length === 0 && (
        <p className="py-6 text-center text-sm text-white/40">Nothing to configure here.</p>
      )}
    </div>
  );
}


