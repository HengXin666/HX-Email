import React, { createContext, useContext, useEffect, useState, useCallback } from 'react'
import type { User, Group, Tag, UsableEmail, Platform, EmailAccount, Overview } from '../types'
import { api } from '../api/client'

interface AppState {
  user: User | null
  token: string | null
  groups: Group[]
  tags: Tag[]
  emails: UsableEmail[]
  platforms: Platform[]
  accounts: EmailAccount[]
  overview: Overview | null
  loading: boolean
}

interface AppContextValue extends AppState {
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  register: (username: string, password: string) => Promise<void>
  updateCredentials: (username: string, password: string) => Promise<User>
  refreshAll: () => Promise<void>
  refreshGroups: () => Promise<void>
  refreshEmails: () => Promise<void>
  refreshPlatforms: () => Promise<void>
  refreshAccounts: () => Promise<void>
  refreshOverview: () => Promise<void>
  createGroup: (name: string, color?: string) => Promise<Group>
  updateGroup: (id: number, name: string, color: string) => Promise<Group>
  deleteGroup: (id: number) => Promise<void>
  createEmail: (address: string, label?: string, groupId?: number | null) => Promise<UsableEmail>
  organizeEmail: (id: number, data: { label?: string; group_id?: number | null; tag_ids?: number[] }) => Promise<UsableEmail>
  createPlatform: (name: string) => Promise<Platform>
  updatePlatform: (id: number, name: string) => Promise<Platform>
  deletePlatform: (id: number) => Promise<void>
  createAccount: (data: { provider: string; primary_address: string; display_name: string; alias_addresses?: string[] }) => Promise<EmailAccount>
  addAlias: (accountId: number, address: string, label?: string) => Promise<UsableEmail>
  createTempMail: (label: string) => Promise<UsableEmail>
}

const AppContext = createContext<AppContextValue | null>(null)

function getStoredToken(): string | null {
  try {
    return window.localStorage?.getItem('hx_token') ?? null
  } catch {
    return null
  }
}

function getStoredUsername(): string {
  try {
    return window.localStorage?.getItem('hx_last_username') ?? ''
  } catch {
    return ''
  }
}

function getStoredUser(): User | null {
  try {
    const raw = window.localStorage?.getItem('hx_user')
    if (!raw) return null
    return JSON.parse(raw) as User
  } catch {
    return null
  }
}

function setStoredToken(token: string): void {
  try {
    window.localStorage?.setItem('hx_token', token)
  } catch {}
}

function setStoredUser(user: User): void {
  try {
    window.localStorage?.setItem('hx_user', JSON.stringify(user))
    window.localStorage?.setItem('hx_last_username', user.username)
  } catch {}
}

function clearStoredToken(): void {
  try {
    window.localStorage?.removeItem('hx_token')
    window.localStorage?.removeItem('hx_user')
  } catch {}
}

function suppressStoredAutoLogin(): void {
  try {
    window.localStorage?.setItem('hx_auto_login', 'false')
  } catch {}
}

export const AppProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const storedUser = getStoredUser()
  const [state, setState] = useState<AppState>({
    user: storedUser,
    token: getStoredToken(),
    groups: [],
    tags: [],
    emails: [],
    platforms: [],
    accounts: [],
    overview: null,
    loading: false
  })

  const refreshGroups = useCallback(async () => {
    const groups = await api.listGroups()
    setState((s) => ({ ...s, groups }))
  }, [])

  const refreshEmails = useCallback(async () => {
    const emails = await api.listUsableEmails()
    setState((s) => ({ ...s, emails }))
  }, [])

  const refreshPlatforms = useCallback(async () => {
    const platforms = await api.listPlatforms()
    setState((s) => ({ ...s, platforms }))
  }, [])

  const refreshAccounts = useCallback(async () => {
    try {
      const accounts = await api.listEmailAccounts()
      setState((s) => ({ ...s, accounts }))
    } catch { /* keep previous accounts on error */ }
  }, [])

  const refreshOverview = useCallback(async () => {
    try {
      const overview = await api.overview()
      setState((s) => ({ ...s, overview }))
    } catch { /* keep previous overview on error */ }
  }, [])

  const refreshTags = useCallback(async () => {
    const tags = await api.listTags()
    setState((s) => ({ ...s, tags }))
  }, [])

  const refreshAll = useCallback(async () => {
    await Promise.allSettled([refreshGroups(), refreshEmails(), refreshPlatforms(), refreshAccounts(), refreshOverview(), refreshTags()])
  }, [refreshGroups, refreshEmails, refreshPlatforms, refreshAccounts, refreshOverview, refreshTags])

  const login = useCallback(async (username: string, password: string) => {
    const res = await api.login(username, password)
    setStoredToken(res.access_token)
    setStoredUser(res.user)
    setState((s) => ({ ...s, token: res.access_token, user: res.user }))
  }, [])

  const register = useCallback(async (username: string, password: string) => {
    const res = await api.register(username, password)
    setStoredToken(res.access_token)
    setStoredUser(res.user)
    setState((s) => ({ ...s, token: res.access_token, user: res.user }))
  }, [])

  const updateCredentials = useCallback(async (username: string, password: string) => {
    const res = await api.updateCredentials(username, password)
    setStoredUser(res.user)
    setState((s) => ({ ...s, user: res.user }))
    return res.user
  }, [])

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {}
    suppressStoredAutoLogin()
    clearStoredToken()
    setState((s) => ({ ...s, token: null, user: null }))
  }, [])

  const createGroup = useCallback(async (name: string, color?: string) => {
    const g = await api.createGroup(name, color)
    await refreshGroups()
    return g
  }, [refreshGroups])

  const updateGroup = useCallback(async (id: number, name: string, color: string) => {
    const g = await api.updateGroup(id, name, color)
    await refreshGroups()
    return g
  }, [refreshGroups])

  const deleteGroup = useCallback(async (id: number) => {
    await api.deleteGroup(id)
    await refreshGroups()
    await refreshEmails()
  }, [refreshGroups, refreshEmails])

  const createEmail = useCallback(async (address: string, label = '', groupId?: number | null) => {
    const e = await api.createUsableEmail(address, label)
    if (groupId) await api.organizeUsableEmail(e.id, { group_id: groupId })
    await refreshEmails()
    return e
  }, [refreshEmails])

  const organizeEmail = useCallback(async (id: number, data: any) => {
    const e = await api.organizeUsableEmail(id, data)
    await refreshEmails()
    return e
  }, [refreshEmails])

  const createPlatform = useCallback(async (name: string) => {
    const p = await api.createPlatform(name)
    await refreshPlatforms()
    return p
  }, [refreshPlatforms])

  const updatePlatform = useCallback(async (id: number, name: string) => {
    const p = await api.updatePlatform(id, name)
    await refreshPlatforms()
    return p
  }, [refreshPlatforms])

  const deletePlatform = useCallback(async (id: number) => {
    await api.deletePlatform(id)
    await refreshPlatforms()
  }, [refreshPlatforms])

  const createAccount = useCallback(async (data: any) => {
    const a = await api.createEmailAccount(data)
    await refreshAccounts()
    await refreshEmails()
    return a
  }, [refreshAccounts, refreshEmails])

  const addAlias = useCallback(async (accountId: number, address: string, label?: string) => {
    const a = await api.addAlias(accountId, address, label)
    await refreshAccounts()
    await refreshEmails()
    return a
  }, [refreshAccounts, refreshEmails])

  const createTempMail = useCallback(async (label: string) => {
    const e = await api.createTempMail(label)
    await refreshEmails()
    return e
  }, [refreshEmails])

  useEffect(() => {
    if (state.token) {
      if (!state.user) {
        setState((s) => ({
          ...s,
          user: { id: 1, username: getStoredUsername(), is_admin: true }
        }))
      }
      refreshAll()
    }
  }, [state.token, state.user, refreshAll])

  useEffect(() => {
    const handler = () => {
      clearStoredToken()
      setState((s) => ({ ...s, token: null, user: null }))
    }
    window.addEventListener('auth:session-expired', handler)
    return () => window.removeEventListener('auth:session-expired', handler)
  }, [])

  return (
    <AppContext.Provider
      value={{
        ...state,
        login,
        logout,
        register,
        updateCredentials,
        refreshAll,
        refreshGroups,
        refreshEmails,
        refreshPlatforms,
        refreshAccounts,
        refreshOverview,
        createGroup,
        updateGroup,
        deleteGroup,
        createEmail,
        organizeEmail,
        createPlatform,
        updatePlatform,
        deletePlatform,
        createAccount,
        addAlias,
        createTempMail
      }}
    >
      {children}
    </AppContext.Provider>
  )
}

export const useApp = () => {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used within AppProvider')
  return ctx
}
