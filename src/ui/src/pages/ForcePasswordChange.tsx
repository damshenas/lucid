import { useState } from "react";
import { api } from "../api/client";
import { Button } from "../components/ui/Button";

interface Props {
  onChanged: () => void;
  onLogout: () => void;
}

/** Blocks the app until a must-change-password account picks a new password —
 * previously the flag from login was silently discarded, so traders only found
 * out via a bare 403 on the first permissioned action they tried (e.g. toggling
 * "use system default credentials"). */
export function ForcePasswordChange({ onChanged, onLogout }: Props) {
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (newPassword !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.changePassword(newPassword);
      onChanged();
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <div className="glass w-full max-w-sm animate-fade-in-up rounded-3xl p-8">
        <div className="mb-1 flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-accent" />
          <h1 className="text-2xl font-bold text-white">Lucid</h1>
        </div>
        <p className="mb-6 text-sm text-white/50">
          Your password must be changed before you can continue.
        </p>
        {error && (
          <p className="mb-4 rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
            {error}
          </p>
        )}
        <form onSubmit={submit} className="space-y-3">
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
          <Button type="submit" disabled={saving} className="w-full">
            {saving ? "Saving…" : "Change password"}
          </Button>
        </form>
        <button
          type="button"
          onClick={onLogout}
          className="mt-4 w-full text-center text-sm text-white/40 hover:text-white/70"
        >
          Log out
        </button>
      </div>
    </div>
  );
}
