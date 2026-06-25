import React from 'react'
import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import { Sidebar } from './components/layout'
import { useApp } from './store/AppContext'

import { Login } from './pages/Login'
import { Overview } from './pages/Overview'
import { Accounts } from './pages/Accounts'
import { Platforms } from './pages/Platforms'
import { TempMail } from './pages/TempMail'
import { TokenTool } from './pages/TokenTool'
import { ApiAccess } from './pages/ApiAccess'
import { Settings } from './pages/Settings'
import { RefreshLogPage } from './pages/RefreshLog'
import { PoolAdmin } from './pages/PoolAdmin'
import { AuditLog } from './pages/AuditLog'

const ProtectedLayout: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const location = useLocation()
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
  )
}

const RequireAuth: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { token } = useApp()
  if (!token) return <Navigate to="/login" replace />
  return <ProtectedLayout>{children}</ProtectedLayout>
}

const App: React.FC = () => {
  const { token } = useApp()

  return (
    <Routes>
      <Route path="/login" element={token ? <Navigate to="/overview" replace /> : <Login />} />
      <Route path="/overview" element={<RequireAuth><Overview /></RequireAuth>} />
      <Route path="/accounts" element={<RequireAuth><Accounts /></RequireAuth>} />
      <Route path="/platforms" element={<RequireAuth><Platforms /></RequireAuth>} />
      <Route path="/temp-mail" element={<RequireAuth><TempMail /></RequireAuth>} />
      <Route path="/token-tool" element={<RequireAuth><TokenTool /></RequireAuth>} />
      <Route path="/api" element={<RequireAuth><ApiAccess /></RequireAuth>} />
      <Route path="/settings" element={<RequireAuth><Settings /></RequireAuth>} />
      <Route path="/refresh-log" element={<RequireAuth><RefreshLogPage /></RequireAuth>} />
      <Route path="/pool-admin" element={<RequireAuth><PoolAdmin /></RequireAuth>} />
      <Route path="/audit" element={<RequireAuth><AuditLog /></RequireAuth>} />
      <Route path="*" element={<Navigate to={token ? '/overview' : '/login'} replace />} />
    </Routes>
  )
}

export default App
