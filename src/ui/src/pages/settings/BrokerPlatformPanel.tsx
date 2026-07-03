import { Badge } from "../../components/ui/Badge";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import { Toggle } from "../../components/ui/Toggle";
import { MyCredentialsTab } from "./MyCredentialsTab";
import type { BrokerPlatform, GroupNode } from "./schemaTree";
import { SystemCredentialsTab } from "./SystemCredentialsTab";

function fieldEntry(node: GroupNode, leaf: string) {
  return node.fields.find((f) => f.key.endsWith(`.${leaf}`));
}

function currentValue(node: GroupNode, leaf: string, edited: Record<string, unknown>): unknown {
  const entry = fieldEntry(node, leaf);
  if (!entry) return undefined;
  return entry.key in edited ? edited[entry.key] : entry.field.value;
}

interface Props {
  platform: BrokerPlatform;
  brokerNode: GroupNode;
  edited: Record<string, unknown>;
  onChange: (key: string, raw: string, type: string) => void;
  readOnly: boolean;
  canSystem: boolean;
  canCredentials: boolean;
}

/** Everything about one broker platform in a single place — whether it's the active
 * broker, paper mode, and its own credentials — instead of splitting those across
 * separate "Settings"/"Credentials" sub-tabs. */
export function BrokerPlatformPanel({
  platform,
  brokerNode,
  edited,
  onChange,
  readOnly,
  canSystem,
  canCredentials,
}: Props) {
  const brokerNameEntry = fieldEntry(brokerNode, "broker_name");
  const paperModeEntry = fieldEntry(brokerNode, "paper_mode");
  const isActive = currentValue(brokerNode, "broker_name", edited) === platform.id;
  const paperMode = Boolean(currentValue(brokerNode, "paper_mode", edited));

  return (
    <div className="space-y-4">
      <Card>
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-white/90">Active broker</p>
            <p className="text-sm text-white/50">
              Use {platform.label} as the trading broker for this asset class.
            </p>
          </div>
          {isActive ? (
            <Badge tone="cyan">Active</Badge>
          ) : (
            <Button
              variant="secondary"
              disabled={readOnly || !brokerNameEntry}
              onClick={() => brokerNameEntry && onChange(brokerNameEntry.key, platform.id, "str")}
            >
              Make active
            </Button>
          )}
        </div>
      </Card>

      {paperModeEntry && (
        <Card>
          <div className="flex items-center justify-between gap-3">
            <span className="text-sm text-white/80">Paper mode (simulate orders, no real trades)</span>
            <Toggle
              checked={paperMode}
              onChange={(checked) => onChange(paperModeEntry.key, String(checked), "bool")}
              disabled={readOnly}
              label="Paper mode"
            />
          </div>
        </Card>
      )}

      {canSystem && <SystemCredentialsTab platform={platform.label} compact />}
      {canCredentials && <MyCredentialsTab platform={platform.label} compact />}
    </div>
  );
}
