import { useState } from "react";

interface Props {
  initialized: boolean | null;
  onLogin: (u: string, p: string) => Promise<void>;
  onSetup: (u: string, p: string) => Promise<void>;
}

export function Login({ initialized, onLogin, onSetup }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const isSetup = initialized === false;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      if (isSetup) await onSetup(username, password);
      else await onLogin(username, password);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div style={{ maxWidth: 320, margin: "10vh auto", fontFamily: "system-ui" }}>
      <h1>Lucid</h1>
      <h3>{isSetup ? "Create first admin" : "Sign in"}</h3>
      <form onSubmit={submit}>
        <input
          placeholder="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          style={{ display: "block", width: "100%", marginBottom: 8 }}
        />
        <input
          type="password"
          placeholder="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          style={{ display: "block", width: "100%", marginBottom: 8 }}
        />
        <button type="submit">{isSetup ? "Create" : "Login"}</button>
      </form>
      {error && <p style={{ color: "crimson" }}>{error}</p>}
    </div>
  );
}
