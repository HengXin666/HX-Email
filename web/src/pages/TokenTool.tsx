import React, { useEffect, useMemo, useState } from 'react'
import { Topbar } from '../components/layout'
import { useApp } from '../store/AppContext'
import { useToast } from '../components/ui/Toast'
import { Button, Card, Input } from '../components/ui/Primitives'
import { IconKey, IconRefresh } from '../components/icons'
import { api } from '../api/client'
import type { TokenConfig, TokenExchangeResult, TokenPrepareResult } from '../types'

const SCOPE_PRESETS = {
  graph: ['offline_access', 'https://graph.microsoft.com/.default'],
  imap: ['offline_access', 'https://outlook.office.com/IMAP.AccessAsUser.All']
}

const DEFAULT_CONFIG: TokenConfig = {
  client_id: '',
  redirect_uri: '',
  scope: SCOPE_PRESETS.imap.join(' '),
  tenant: 'consumers',
  prompt_consent: true
}

const defaultRedirectUri = () => `${window.location.origin}/token-tool/callback`

const parseScopes = (value: string) =>
  value
    .split(/[\s,;]+/)
    .map((item) => item.trim())
    .filter(Boolean)

const normalizeScope = (value: string) => {
  const tokens = new Set(parseScopes(value))
  tokens.add('offline_access')
  return Array.from(tokens).join(' ')
}

export const TokenTool: React.FC = () => {
  const { refreshAccounts, refreshEmails } = useApp()
  const { toast } = useToast()
  const [config, setConfig] = useState<TokenConfig>(DEFAULT_CONFIG)
  const [prepared, setPrepared] = useState<TokenPrepareResult | null>(null)
  const [callbackUrl, setCallbackUrl] = useState('')
  const [tokens, setTokens] = useState<TokenExchangeResult | null>(null)
  const [accounts, setAccounts] = useState<Array<{ id: number; email: string; status: string }>>([])
  const [saveMode, setSaveMode] = useState<'update' | 'create'>('update')
  const [accountId, setAccountId] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [scopeEntry, setScopeEntry] = useState('')
  const [loading, setLoading] = useState<string | null>(null)

  const scopeTokens = useMemo(() => parseScopes(config.scope), [config.scope])

  useEffect(() => {
    void loadInitial()
  }, [])

  const loadInitial = async () => {
    try {
      const [remoteConfig, remoteAccounts] = await Promise.all([
        api.getTokenToolConfig(),
        api.listTokenToolAccounts()
      ])
      setConfig({
        ...remoteConfig,
        redirect_uri: remoteConfig.redirect_uri || defaultRedirectUri(),
        scope: normalizeScope(remoteConfig.scope || DEFAULT_CONFIG.scope),
        tenant: 'consumers'
      })
      setAccounts(remoteAccounts)
    } catch (err: any) {
      toast(err.message, 'error')
    }
  }

  const patchConfig = (key: keyof TokenConfig, value: string | boolean) => {
    setConfig((current) => ({ ...current, [key]: value }))
  }

  const setScopePreset = (preset: keyof typeof SCOPE_PRESETS) => {
    patchConfig('scope', SCOPE_PRESETS[preset].join(' '))
  }

  const addScope = () => {
    patchConfig('scope', normalizeScope(`${config.scope} ${scopeEntry}`))
    setScopeEntry('')
  }

  const removeScope = (scope: string) => {
    if (scope === 'offline_access') return
    patchConfig('scope', normalizeScope(scopeTokens.filter((item) => item !== scope).join(' ')))
  }

  const handleSaveConfig = async () => {
    setLoading('config')
    try {
      const saved = await api.saveTokenToolConfig(config)
      setConfig(saved)
      toast('配置已保存', 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(null)
    }
  }

  const handlePrepare = async () => {
    setLoading('prepare')
    try {
      const result = await api.prepareTokenTool(config)
      setPrepared(result)
      window.open(result.authorize_url, '_blank', 'noopener,noreferrer')
      toast('授权链接已生成', 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(null)
    }
  }

  const handleExchange = async () => {
    setLoading('exchange')
    try {
      const result = await api.exchangeTokenTool({ callback_url: callbackUrl })
      setTokens(result)
      toast('refresh_token 已获取', 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(null)
    }
  }

  const handleSaveToken = async () => {
    if (!tokens) return
    setLoading('save')
    try {
      await api.saveTokenTool({
        mode: saveMode,
        account_id: saveMode === 'update' ? Number(accountId) : null,
        email: saveMode === 'create' ? newEmail : undefined,
        client_id: tokens.client_id,
        refresh_token: tokens.refresh_token
      })
      await Promise.all([refreshAccounts(), refreshEmails(), loadInitial()])
      toast(saveMode === 'create' ? 'Outlook 账号已创建' : 'Token 已保存到账号', 'success')
    } catch (err: any) {
      toast(err.message, 'error')
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="flex-1 flex flex-col min-w-0">
      <Topbar title="Token 工具" subtitle="Outlook refresh_token 获取与写入" />
      <div className="flex-1 overflow-auto">
        <div className="max-w-5xl mx-auto p-6 space-y-5">
          <Card className="p-5">
            <div className="flex items-center justify-between gap-3 mb-4">
              <h2 className="text-sm font-semibold text-gh-text flex items-center gap-2">
                <IconKey size={14} /> OAuth 配置
              </h2>
              <Button variant="ghost" onClick={loadInitial}>
                <IconRefresh size={14} /> 刷新
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input label="Client ID" value={config.client_id} onChange={(e) => patchConfig('client_id', e.target.value)} />
              <Input label="Redirect URI" value={config.redirect_uri} onChange={(e) => patchConfig('redirect_uri', e.target.value)} />
              <Input label="Tenant" value="consumers" readOnly />
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-medium text-gh-text-muted">Scope 预设</label>
                <div className="flex gap-2">
                  <Button variant="secondary" size="sm" onClick={() => setScopePreset('imap')}>
                    IMAP
                  </Button>
                  <Button variant="secondary" size="sm" onClick={() => setScopePreset('graph')}>
                    Graph 邮件
                  </Button>
                </div>
              </div>
            </div>
            <div className="mt-3 rounded-md border border-gh-border bg-gh-canvas-inset p-3">
              <div className="mb-2 flex flex-wrap gap-2">
                {scopeTokens.map((scope) => (
                  <span
                    key={scope}
                    className="inline-flex items-center gap-1 rounded-md border border-gh-border bg-gh-canvas px-2 py-1 text-xs text-gh-text"
                  >
                    {scope}
                    {scope === 'offline_access' ? (
                      <span className="text-gh-text-secondary">锁定</span>
                    ) : (
                      <button
                        type="button"
                        className="text-gh-text-secondary hover:text-gh-danger"
                        onClick={() => removeScope(scope)}
                      >
                        ×
                      </button>
                    )}
                  </span>
                ))}
              </div>
              <div className="flex gap-2">
                <Input
                  value={scopeEntry}
                  onChange={(e) => setScopeEntry(e.target.value)}
                  placeholder="输入 scope，支持空格 / 逗号 / 分号分隔"
                  className="flex-1"
                />
                <Button variant="secondary" onClick={addScope} disabled={!scopeEntry.trim()}>
                  添加
                </Button>
              </div>
              <div className="mt-2 text-xs text-gh-text-secondary">
                默认使用参考项目的 IMAP 预设：offline_access + IMAP.AccessAsUser.All。
              </div>
            </div>
            <label className="mt-3 flex items-center gap-2 text-sm text-gh-text-muted">
              <input
                type="checkbox"
                checked={config.prompt_consent}
                onChange={(e) => patchConfig('prompt_consent', e.target.checked)}
              />
              强制重新授权
            </label>
            <div className="mt-4 flex flex-wrap gap-2">
              <Button variant="secondary" onClick={handleSaveConfig} loading={loading === 'config'}>
                保存配置
              </Button>
              <Button variant="primary" onClick={handlePrepare} loading={loading === 'prepare'}>
                生成授权链接
              </Button>
              {prepared && (
                <a
                  className="inline-flex items-center rounded-md border border-gh-border px-3 py-1.5 text-sm text-gh-accent hover:bg-gh-accent/10"
                  href={prepared.authorize_url}
                  target="_blank"
                  rel="noreferrer"
                >
                  打开授权链接
                </a>
              )}
            </div>
          </Card>

          <Card className="p-5">
            <h2 className="text-sm font-semibold text-gh-text mb-4">回调与保存</h2>
            <textarea
              value={callbackUrl}
              onChange={(e) => setCallbackUrl(e.target.value)}
              className="w-full min-h-24 bg-gh-canvas-inset border border-gh-border rounded-md px-3 py-2 text-sm text-gh-text font-mono focus:outline-none focus:border-gh-accent"
              placeholder="粘贴 /token-tool/callback?code=...&state=... 的完整回调 URL"
            />
            <div className="mt-3">
              <Button variant="secondary" onClick={handleExchange} loading={loading === 'exchange'}>
                换取 refresh_token
              </Button>
            </div>
            {tokens && (
              <div className="mt-5 space-y-3 rounded-md border border-gh-border bg-gh-canvas-inset p-4">
                <Input label="Refresh Token" value={tokens.refresh_token} readOnly className="font-mono" />
                <div className="grid grid-cols-[180px_1fr_auto] gap-3 items-end">
                  <div className="flex flex-col gap-1.5">
                    <label className="text-xs font-medium text-gh-text-muted">写入方式</label>
                    <select
                      value={saveMode}
                      onChange={(e) => setSaveMode(e.target.value as 'update' | 'create')}
                      className="bg-gh-canvas border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text"
                    >
                      <option value="update">更新已有账号</option>
                      <option value="create">新建 Outlook 账号</option>
                    </select>
                  </div>
                  {saveMode === 'update' ? (
                    <div className="flex flex-col gap-1.5">
                      <label className="text-xs font-medium text-gh-text-muted">Outlook 账号</label>
                      <select
                        value={accountId}
                        onChange={(e) => setAccountId(e.target.value)}
                        className="bg-gh-canvas border border-gh-border rounded-md px-3 py-1.5 text-sm text-gh-text"
                      >
                        <option value="">选择账号</option>
                        {accounts.map((account) => (
                          <option key={account.id} value={account.id}>
                            {account.email}
                          </option>
                        ))}
                      </select>
                    </div>
                  ) : (
                    <Input label="邮箱地址" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} />
                  )}
                  <Button
                    variant="primary"
                    onClick={handleSaveToken}
                    loading={loading === 'save'}
                    disabled={saveMode === 'update' ? !accountId : !newEmail}
                  >
                    保存 refresh_token
                  </Button>
                </div>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  )
}
