import { Navigate, Route, Routes } from "react-router-dom";
import { AppLayout } from "./components/AppLayout";
import { RequirePermission } from "./components/RequirePermission";
import { ServerStatusGate } from "./components/ServerStatusGate";
import { useAuth } from "./hooks/useAuth";
import { defaultPathFor } from "./lib/nav";
import { Backtesting } from "./pages/Backtesting";
import { Dashboard } from "./pages/Dashboard";
import { Jobs } from "./pages/Jobs";
import { Login } from "./pages/Login";
import { Orders } from "./pages/Orders";
import { Positions } from "./pages/Positions";
import { Prices } from "./pages/Prices";
import { Settings } from "./pages/Settings";
import { Signals } from "./pages/Signals";
import { Strategies } from "./pages/Strategies";
import { Users } from "./pages/Users";

export function App() {
  const { token, role, initialized, login, setup, logout } = useAuth();

  if (!token) {
    return (
      <ServerStatusGate>
        <Login initialized={initialized} onLogin={login} onSetup={setup} />
      </ServerStatusGate>
    );
  }

  return (
    <ServerStatusGate>
      <Routes>
        <Route path="/" element={<AppLayout role={role} onLogout={logout} />}>
          <Route
            index
            element={
              <RequirePermission role={role} permission="view_trading">
                <Dashboard />
              </RequirePermission>
            }
          />
          <Route
            path="positions"
            element={
              <RequirePermission role={role} permission="view_trading">
                <Positions />
              </RequirePermission>
            }
          />
          <Route
            path="signals"
            element={
              <RequirePermission role={role} permission="view_trading">
                <Signals />
              </RequirePermission>
            }
          />
          <Route
            path="orders"
            element={
              <RequirePermission role={role} permission="view_trading">
                <Orders />
              </RequirePermission>
            }
          />
          <Route
            path="prices"
            element={
              <RequirePermission role={role} permission="view_trading">
                <Prices />
              </RequirePermission>
            }
          />
          <Route
            path="strategies"
            element={
              <RequirePermission role={role} permission="edit_own_strategies">
                <Strategies />
              </RequirePermission>
            }
          />
          <Route
            path="backtesting"
            element={
              <RequirePermission role={role} permission="edit_own_strategies">
                <Backtesting />
              </RequirePermission>
            }
          />
          <Route path="settings" element={<Settings />} />
          <Route
            path="jobs"
            element={
              <RequirePermission role={role} permission="manage_users">
                <Jobs />
              </RequirePermission>
            }
          />
          <Route
            path="users"
            element={
              <RequirePermission role={role} permission="manage_users">
                <Users />
              </RequirePermission>
            }
          />
          <Route path="*" element={<Navigate to={defaultPathFor(role)} replace />} />
        </Route>
      </Routes>
    </ServerStatusGate>
  );
}
