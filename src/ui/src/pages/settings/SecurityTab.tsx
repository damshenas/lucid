import { useState } from "react";
import { api } from "../../api/client";
import { Button } from "../../components/ui/Button";
import { Card } from "../../components/ui/Card";

interface Status {
  text: string;
  tone: "success" | "error";
}

export function SecurityTab() {
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<Status | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword !== confirm) {
      setStatus({ text: "Passwords do not match.", tone: "error" });
      return;
    }
    setSaving(true);
    setStatus(null);
    try {
      await api.changePassword(newPassword);
      setNewPassword("");
      setConfirm("");
      setStatus({ text: "Password changed.", tone: "success" });
    } catch (e) {
      setStatus({ text: (e as Error).message, tone: "error" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-white/40">
        Change password
      </h3>
      {status && (
        <p
          className={`mb-3 rounded-xl border px-3 py-2 text-sm ${
            status.tone === "success"
              ? "border-cyan/30 bg-cyan/10 text-cyan"
              : "border-rose/30 bg-rose/10 text-rose"
          }`}
        >
          {status.text}
        </p>
      )}
      <form onSubmit={submit} className="max-w-sm space-y-3">
        <label className="block">
          <span className="mb-1 block text-sm text-white/80">New password</span>
          <input
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
            minLength={8}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-sm text-white/80">Confirm new password</span>
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            required
            minLength={8}
            className="w-full rounded-xl border border-white/10 bg-white/5 px-3.5 py-2 text-sm text-white outline-none transition-colors focus:border-violet/50 focus:glow-violet"
          />
        </label>
        <Button type="submit" disabled={saving}>
          {saving ? "Saving…" : "Change password"}
        </Button>
      </form>
    </Card>
  );
}
