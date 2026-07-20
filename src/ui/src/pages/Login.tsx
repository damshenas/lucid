import { useState } from "react";
import { Lock, User } from "lucide-react";
import { Button } from "../components/ui/Button";

interface Props {
  initialized: boolean | null;
  sessionExpired: boolean;
  onLogin: (u: string, p: string) => Promise<void>;
  onSetup: (u: string, p: string) => Promise<void>;
}

export function Login({ initialized, sessionExpired, onLogin, onSetup }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const isSetup = initialized === false;

  // Best-effort: asks the browser's own password manager to offer saving these
  // credentials (Credential Management API). We never persist the raw password
  // ourselves — the browser's manager is the only thing that stores it.
  async function offerToSaveCredential(id: string, pwd: string) {
    const PasswordCredentialCtor = (
      window as unknown as { PasswordCredential?: new (data: Record<string, unknown>) => Credential }
    ).PasswordCredential;
    if (!PasswordCredentialCtor || !navigator.credentials?.store) return;
    try {
      const credential = new PasswordCredentialCtor({ id, password: pwd, name: id });
      await navigator.credentials.store(credential);
    } catch {
      // Browser may decline or not fully support this — safe to ignore.
    }
  }

  async function submit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    // Read the submitted values straight from the DOM (FormData) instead of
    // trusting the controlled `username`/`password` state. Some browsers'
    // autofill / password-manager extensions set an input's value without
    // dispatching a React-visible input/change event, so the state variable can
    // still be empty on the very first submit even though the fields visibly show
    // the autofilled text — that made the first login/setup click silently no-op
    // (empty credentials rejected) and only a second click, after some later event
    // (e.g. the user's own keystroke or a blur) synced the state, actually worked.
    const data = new FormData(e.currentTarget);
    const u = String(data.get("username") ?? "");
    const p = String(data.get("password") ?? "");
    try {
      if (isSetup) await onSetup(u, p);
      else await onLogin(u, p);
      await offerToSaveCredential(u, p);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
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
          {isSetup ? "Create the first admin account" : "Sign in to continue"}
        </p>

        {sessionExpired && (
          <p className="mb-4 rounded-xl border border-cyan/30 bg-cyan/10 px-3 py-2 text-sm text-cyan">
            Your session expired. Please sign in again.
          </p>
        )}

        <form onSubmit={submit} autoComplete="on" className="space-y-3">
          <label className="block">
            <span className="sr-only">Username</span>
            <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3.5 py-2.5 transition-colors focus-within:border-violet/50 focus-within:glow-violet">
              <User size={16} className="text-white/40" />
              <input
                id="username"
                name="username"
                placeholder="Username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                className="w-full bg-transparent text-sm text-white placeholder:text-white/30 outline-none"
              />
            </div>
          </label>
          <label className="block">
            <span className="sr-only">Password</span>
            <div className="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/5 px-3.5 py-2.5 transition-colors focus-within:border-violet/50 focus-within:glow-violet">
              <Lock size={16} className="text-white/40" />
              <input
                id="password"
                name="password"
                type="password"
                placeholder="Password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete={isSetup ? "new-password" : "current-password"}
                className="w-full bg-transparent text-sm text-white placeholder:text-white/30 outline-none"
              />
            </div>
          </label>

          {error && (
            <p className="rounded-xl border border-rose/30 bg-rose/10 px-3 py-2 text-sm text-rose">
              {error}
            </p>
          )}

          <Button type="submit" disabled={busy} className="w-full">
            {busy ? "Please wait…" : isSetup ? "Create account" : "Sign in"}
          </Button>
        </form>
      </div>
    </div>
  );
}
