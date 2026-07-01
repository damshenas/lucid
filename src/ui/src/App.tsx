import { useState } from "react";
import { Nav } from "./components/Nav";
import { useAuth } from "./hooks/useAuth";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { Settings } from "./pages/Settings";
import { Strategies } from "./pages/Strategies";

export function App() {
  const { token, initialized, login, setup, logout } = useAuth();
  const [view, setView] = useState("dashboard");

  if (!token) {
    return <Login initialized={initialized} onLogin={login} onSetup={setup} />;
  }

  return (
    <div style={{ fontFamily: "system-ui", maxWidth: 900, margin: "0 auto" }}>
      <Nav current={view} onNavigate={setView} onLogout={logout} />
      <main style={{ padding: 16 }}>
        {view === "dashboard" && <Dashboard />}
        {view === "strategies" && <Strategies />}
        {view === "settings" && <Settings />}
      </main>
    </div>
  );
}
