import { useState } from "react";
import { api } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";
import type { GroupNode } from "./schemaTree";
import { SchemaGroup } from "./SchemaGroup";

interface Props {
  gitSyncNode: GroupNode;
  edited: Record<string, unknown>;
  onChange: (key: string, raw: string, type: string) => void;
  readOnly: boolean;
}

/** Git Sync tab: a "Sync now" button that pulls EXT_STRATEGIES (an already-cloned git
 * checkout — its remote/branch is configured out-of-band on the host, not here) and
 * deploys new strategy files, plus the `enabled` toggle that only controls whether
 * this also runs automatically once at container startup.
 *
 * "Sync now" always works regardless of `enabled` and regardless of whether pending
 * `edited` changes have been saved yet — clicking it is itself the admin's consent,
 * it must never depend on a separate setting having been saved first via the page's
 * shared "Save changes" button (see POST /api/v1/admin/git-sync). */
export function GitSyncTab({ gitSyncNode, edited, onChange, readOnly }: Props) {
  const [syncing, setSyncing] = useState(false);
  const [result, setResult] = useState<{ text: string; tone: "success" | "error" } | null>(null);

  async function syncNow() {
    setSyncing(true);
    setResult(null);
    try {
      const { commit, deployed } = await api.gitSync();
      setResult({
        text:
          deployed.length > 0
            ? `Synced to ${commit.slice(0, 8)} — ${deployed.length} file(s) updated.`
            : `Synced to ${commit.slice(0, 8)} — no changes.`,
        tone: "success",
      });
    } catch (e) {
      setResult({ text: (e as Error).message, tone: "error" });
    } finally {
      setSyncing(false);
    }
  }

  return (
    <div className="space-y-4">
      <Card>
        <div className="space-y-3">
          <div>
            <p className="text-sm font-medium text-white/90">Sync now</p>
            <p className="text-sm text-white/50">
              Pulls the EXT_STRATEGIES checkout (its remote/branch must already be set
              up on the host) and deploys any new or updated{" "}
              <code className="mx-1 rounded bg-white/10 px-1 py-0.5">buy/</code>
              and <code className="mx-1 rounded bg-white/10 px-1 py-0.5">sell/</code>
              files. On-demand only — always runs immediately when clicked, whether or
              not "Enabled" below is turned on or saved.
            </p>
          </div>
          <Button variant="secondary" onClick={syncNow} disabled={syncing}>
            {syncing ? "Syncing…" : "Sync now"}
          </Button>
          {result && (
            <div
              className={`rounded-xl border px-3 py-2 text-sm ${
                result.tone === "success"
                  ? "border-cyan/30 bg-cyan/10 text-cyan"
                  : "border-rose/30 bg-rose/10 text-rose"
              }`}
            >
              {result.text}
            </div>
          )}
        </div>
      </Card>

      <p className="text-sm text-white/50">
        "Enabled" below only controls whether this also runs automatically once at
        container startup — remember to hit the page's "Save changes" button for it to
        take effect.
      </p>
      <SchemaGroup node={gitSyncNode} edited={edited} onChange={onChange} readOnly={readOnly} />
    </div>
  );
}
