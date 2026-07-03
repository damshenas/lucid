import { Badge } from "../../components/ui/Badge";
import { Card } from "../../components/ui/Card";
import { Tabs } from "../../components/ui/Tabs";
import { Toggle } from "../../components/ui/Toggle";
import type { Strategy } from "../../types";
import { SchemaGroup } from "./SchemaGroup";
import { emptyGroup, humanize, type GroupNode } from "./schemaTree";

interface Props {
  strategyNode: GroupNode; // tree.strategy — direct fields (active_*_strategy) plus one nested group per discovered strategy
  strategies: Strategy[]; // every discovered strategy (both directions), from GET /api/v1/strategies
  edited: Record<string, unknown>;
  onChange: (key: string, raw: string, type: string) => void;
  readOnly: boolean;
}

function activeName(strategyNode: GroupNode, edited: Record<string, unknown>, direction: "buy" | "sell"): string {
  const key = `strategy.active_${direction}_strategy`;
  if (key in edited) return String(edited[key] ?? "");
  const field = strategyNode.fields.find((f) => f.key === key);
  return field ? String(field.field.value ?? "") : "";
}

function SingleStrategyPanel({
  strategy,
  node,
  isActive,
  readOnly,
  edited,
  onChange,
}: {
  strategy: Strategy;
  node: GroupNode;
  isActive: boolean;
  readOnly: boolean;
  edited: Record<string, unknown>;
  onChange: (key: string, raw: string, type: string) => void;
}) {
  const key = `strategy.active_${strategy.direction}_strategy`;
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-white/90">
              Active {strategy.direction} strategy
            </p>
            {strategy.description && <p className="text-sm text-white/50">{strategy.description}</p>}
          </div>
          <Toggle
            checked={isActive}
            onChange={(checked) => onChange(key, checked ? strategy.name : "", "str")}
            disabled={readOnly}
            label={`Active ${strategy.direction} strategy`}
          />
        </div>
      </Card>
      <SchemaGroup node={node} edited={edited} onChange={onChange} readOnly={readOnly} />
    </div>
  );
}

/** Strategy tab: shows which strategy is active per direction as a plain label (not
 * a dropdown — activation happens per-strategy below instead), then one nested tab
 * per *available* strategy (active or not), each with its own activate toggle and
 * config fields. */
export function StrategyTab({ strategyNode, strategies, edited, onChange, readOnly }: Props) {
  const activeBuy = activeName(strategyNode, edited, "buy");
  const activeSell = activeName(strategyNode, edited, "sell");

  return (
    <div className="space-y-4">
      <Card>
        <div className="space-y-1 text-sm text-white/80">
          <p>
            Active buy strategy:{" "}
            <Badge tone={activeBuy ? "cyan" : "neutral"}>{activeBuy || "None"}</Badge>
          </p>
          <p>
            Active sell strategy:{" "}
            <Badge tone={activeSell ? "cyan" : "neutral"}>{activeSell || "None"}</Badge>
          </p>
        </div>
      </Card>

      {strategies.length === 0 ? (
        <p className="py-6 text-center text-sm text-white/40">Loading…</p>
      ) : (
        <Tabs
          level="nested"
          tabs={strategies.map((strategy) => ({
            id: strategy.name,
            label: humanize(strategy.name),
            content: (
              <SingleStrategyPanel
                strategy={strategy}
                node={strategyNode.groups[strategy.name] ?? emptyGroup()}
                isActive={(strategy.direction === "buy" ? activeBuy : activeSell) === strategy.name}
                readOnly={readOnly}
                edited={edited}
                onChange={onChange}
              />
            ),
          }))}
        />
      )}
    </div>
  );
}
