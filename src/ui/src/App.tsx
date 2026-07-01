import { useState } from "react";
import { LogOut } from "lucide-react";
import { BottomNav } from "./components/BottomNav";
import { IconButton } from "./components/ui/IconButton";
import { useAuth } from "./hooks/useAuth";
import { Dashboard } from "./pages/Dashboard";
import { Login } from "./pages/Login";
import { Settings } from "./pages/Settings";
import { Strategies } from "./pages/Strategies";

const TITLES: Record<string, string> = {
  dashboard: "Dashboard",
  strategies: "Strategies",
  settings: "Settings",
};

export function App() {
  const { token, initialized, login, setup, logout } = useAuth();
  const [view, setView] = useState("dashboard");

  if (!token) {
    return <Login initialized={initialized} onLogin={login} onSetup={setup} />;
  }

  return (
    <div className="min-h-screen">
      <header className="glass sticky top-0 z-10 flex items-center justify-between px-4 py-3 sm:px-6">
        <div className="flex items-center gap-2">
          <span className="h-2 w-2 rounded-full bg-gradient-to-r from-violet to-cyan" />
          <span className="text-lg font-semibold tracking-tight">
            Lucid <span className="text-white/40 font-normal">/ {TITLES[view]}</span>
          </span>
        </div>
        <IconButton icon={<LogOut size={18} />} label="Log out" onClick={logout} />
      </header>

      <main className="mx-auto max-w-2xl px-4 pb-28 pt-4 sm:px-6">
        {view === "dashboard" && <Dashboard />}
        {view === "strategies" && <Strategies />}
        {view === "settings" && <Settings />}
      </main>

      <BottomNav current={view} onNavigate={setView} />
    </div>
  );
}
