import { AnimatePresence, motion } from "framer-motion";
import React from "react";
import { Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Sidebar } from "./components/layout";
import { useBrowserNotifications } from "./hooks/useBrowserNotifications";
import { Accounts } from "./pages/Accounts";
import { ApiAccess } from "./pages/ApiAccess";
import { AuditLog } from "./pages/AuditLog";
import { Home } from "./pages/Home";
import { Login } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { Platforms } from "./pages/Platforms";
import { PoolAdmin } from "./pages/PoolAdmin";
import { Privacy } from "./pages/Privacy";
import { RefreshLogPage } from "./pages/RefreshLog";
import { SendMail } from "./pages/SendMail";
import { Settings } from "./pages/Settings";
import { TempMail } from "./pages/TempMail";
import { Terms } from "./pages/Terms";
import { TokenTool } from "./pages/TokenTool";
import { useApp } from "./store/AppContext";

const ProtectedLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation();
  return (
    <div className="flex h-screen overflow-hidden bg-gh-canvas">
      <Sidebar />
      <AnimatePresence mode="wait">
        <motion.main
          key={location.pathname}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="flex-1 flex flex-col min-w-0 overflow-hidden"
        >
          {children}
        </motion.main>
      </AnimatePresence>
    </div>
  );
};

const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token } = useApp();
  if (!token) return <Navigate to="/login" replace />;
  return <ProtectedLayout>{children}</ProtectedLayout>;
};

const App: React.FC = () => {
  const { token, user } = useApp();
  useBrowserNotifications(!!token, user?.id);

  return (
    <Routes>
      <Route path="/login" element={token ? <Navigate to="/overview" replace /> : <Login />} />
      <Route path="/home" element={<Home />} />
      <Route path="/home/" element={<Home />} />
      <Route path="/home.html" element={<Home />} />
      <Route path="/privacy" element={<Privacy lang="en" />} />
      <Route path="/privacy/" element={<Privacy lang="en" />} />
      <Route path="/privacy-policy" element={<Privacy lang="en" />} />
      <Route path="/privacy.html" element={<Privacy lang="en" />} />
      <Route path="/privacy/zh" element={<Privacy lang="zh" />} />
      <Route path="/terms" element={<Terms lang="en" />} />
      <Route path="/terms/" element={<Terms lang="en" />} />
      <Route path="/terms-of-service" element={<Terms lang="en" />} />
      <Route path="/terms.html" element={<Terms lang="en" />} />
      <Route path="/terms/zh" element={<Terms lang="zh" />} />
      <Route
        path="/overview"
        element={
          <RequireAuth>
            <Overview />
          </RequireAuth>
        }
      />
      <Route
        path="/accounts"
        element={
          <RequireAuth>
            <Accounts />
          </RequireAuth>
        }
      />
      <Route
        path="/send-mail"
        element={
          <RequireAuth>
            <SendMail />
          </RequireAuth>
        }
      />
      <Route
        path="/platforms"
        element={
          <RequireAuth>
            <Platforms />
          </RequireAuth>
        }
      />
      <Route
        path="/temp-mail"
        element={
          <RequireAuth>
            <TempMail />
          </RequireAuth>
        }
      />
      <Route
        path="/token-tool"
        element={
          <RequireAuth>
            <TokenTool />
          </RequireAuth>
        }
      />
      <Route
        path="/api"
        element={
          <RequireAuth>
            <ApiAccess />
          </RequireAuth>
        }
      />
      <Route
        path="/settings"
        element={
          <RequireAuth>
            <Settings />
          </RequireAuth>
        }
      />
      <Route
        path="/refresh-log"
        element={
          <RequireAuth>
            <RefreshLogPage />
          </RequireAuth>
        }
      />
      <Route
        path="/pool-admin"
        element={
          <RequireAuth>
            <PoolAdmin />
          </RequireAuth>
        }
      />
      <Route
        path="/audit"
        element={
          <RequireAuth>
            <AuditLog />
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to={token ? "/overview" : "/home"} replace />} />
    </Routes>
  );
};

export default App;
