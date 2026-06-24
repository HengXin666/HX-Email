import React, { useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { useApp } from '../store/AppContext'
import { useToast } from '../components/ui/Toast'
import slidingBack from '../assets/sliding-back.jpg'
import slidingForm from '../assets/sliding-form.png'
import { AuthButton, FloatingInput } from './impl/LoginControls'
import { getStoredPrefs, persistLoginPrefs } from './impl/login_prefs'

type Mode = 'login' | 'register'

export const Login: React.FC = () => {
  const prefs = useMemo(() => getStoredPrefs(), [])
  const [mode, setMode] = useState<Mode>('login')
  const [username, setUsername] = useState(prefs.username)
  const [password, setPassword] = useState(prefs.password)
  const [registerUsername, setRegisterUsername] = useState('')
  const [registerPassword, setRegisterPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [rememberPassword, setRememberPassword] = useState(prefs.rememberPassword)
  const [autoLogin, setAutoLogin] = useState(prefs.autoLogin)
  const [loading, setLoading] = useState(false)
  const autoLoginTried = useRef(false)
  const { login, register } = useApp()
  const { toast } = useToast()
  const navigate = useNavigate()

  const canLogin = username.trim() !== '' && password !== ''
  const canRegister =
    registerUsername.trim() !== '' &&
    registerPassword !== '' &&
    registerPassword === confirmPassword

  const handleLogin = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!canLogin || loading) return
    setLoading(true)
    try {
      await login(username, password)
      persistLoginPrefs(username, password, rememberPassword, autoLogin)
      toast('登录成功，欢迎回来', 'success')
      navigate('/overview')
    } catch (err: any) {
      toast(err.message || '登录失败', 'error')
      setLoading(false)
    }
  }

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!canRegister || loading) return
    setLoading(true)
    try {
      await register(registerUsername, registerPassword)
      persistLoginPrefs(registerUsername, registerPassword, rememberPassword, autoLogin)
      toast('注册成功，已登录', 'success')
      navigate('/overview')
    } catch (err: any) {
      toast(err.message || '注册失败', 'error')
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!prefs.autoLogin || autoLoginTried.current) return
    autoLoginTried.current = true
    void handleLogin()
  }, [])

  useEffect(() => {
    try {
      if (window.sessionStorage?.getItem('hx_session_expired')) {
        window.sessionStorage?.removeItem('hx_session_expired')
        toast('登录已过期，请重新登录', 'info')
      }
    } catch {}
  }, [toast])

  return (
    <div
      className="min-h-screen flex items-center justify-center overflow-hidden bg-cover bg-center px-4 py-10"
      style={{ backgroundImage: `url(${slidingBack})` }}
    >
      <div className="relative flex items-center justify-center w-full max-w-[860px] min-h-[600px]">
        <motion.div
          animate={{
            height: mode === 'login' ? 560 : 430,
            opacity: mode === 'login' ? 1 : 0.58,
            scale: mode === 'login' ? 1 : 0.96
          }}
          transition={{ duration: 0.45, ease: 'easeInOut' }}
          className={`${mode === 'login' ? 'z-30' : 'z-10'} mx-2 flex h-[560px] w-full max-w-[400px] flex-col items-start justify-center rounded-[10px] border border-white/15 bg-[#111928]/75 px-10 py-10 shadow-[50px_50px_100px_-20px_rgba(50,50,93,0.25),30px_30px_60px_-30px_rgba(0,0,0,0.5),2px_-2px_6px_0_rgba(212,217,222,0.35)_inset] backdrop-blur-xl transition-[z-index] ${mode !== 'login' ? 'pointer-events-none' : ''}`}
          aria-hidden={mode !== 'login'}
        >
          <form onSubmit={handleLogin} className="flex w-full flex-col items-start">
            <div className="text-2xl font-light tracking-wide text-[#f6f0ff]">
              欢迎<b>回来</b>
            </div>
            <div className="mb-9 text-sm tracking-wide text-[#f6f0ff]">登录您的账户</div>

            <FloatingInput
              label="用户名"
              value={username}
              onChange={setUsername}
              disabled={mode !== 'login'}
              autoFocus
            />
            <FloatingInput
              label="密码"
              type="password"
              value={password}
              onChange={setPassword}
              disabled={mode !== 'login'}
            />

            <div className="mb-5 grid w-full grid-cols-2 gap-3 text-xs text-[#f6f9ff]">
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={rememberPassword}
                  onChange={(event) => {
                    const checked = event.target.checked
                    setRememberPassword(checked)
                    if (!checked) setAutoLogin(false)
                  }}
                  disabled={mode !== 'login'}
                  className="h-4 w-4 accent-[#24d97f]"
                />
                记住密码
              </label>
              <label className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={autoLogin}
                  onChange={(event) => {
                    const checked = event.target.checked
                    setAutoLogin(checked)
                    if (checked) setRememberPassword(true)
                  }}
                  disabled={mode !== 'login'}
                  className="h-4 w-4 accent-[#24d97f]"
                />
                自动登录
              </label>
            </div>

            <AuthButton disabled={!canLogin || mode !== 'login'} loading={loading}>
              登录
            </AuthButton>
          </form>
        </motion.div>

        <motion.div
          animate={{
            height: mode === 'register' ? 560 : 430,
            opacity: mode === 'register' ? 1 : 0.58,
            scale: mode === 'register' ? 1 : 0.96
          }}
          transition={{ duration: 0.45, ease: 'easeInOut' }}
          className={`${mode === 'register' ? 'z-30' : 'z-10'} mx-2 flex h-[430px] w-full max-w-[400px] flex-col items-start justify-center rounded-[10px] border border-white/15 bg-[#111928]/75 px-10 py-10 shadow-none backdrop-blur-xl transition-[z-index] ${mode !== 'register' ? 'pointer-events-none' : ''}`}
          aria-hidden={mode !== 'register'}
        >
          <form onSubmit={handleRegister} className="flex w-full flex-col items-start">
            <div className="text-2xl font-light tracking-wide text-[#f6f0ff]">开始</div>
            <div className="mb-9 text-sm tracking-wide text-[#f6f0ff]">创建您的账户</div>

            <FloatingInput
              label="用户名"
              ariaLabel="注册用户名"
              value={registerUsername}
              onChange={setRegisterUsername}
              disabled={mode !== 'register'}
            />
            <FloatingInput
              label="密码"
              ariaLabel="注册密码"
              type="password"
              value={registerPassword}
              onChange={setRegisterPassword}
              disabled={mode !== 'register'}
            />
            <FloatingInput
              label="确认密码"
              ariaLabel="注册确认密码"
              type="password"
              value={confirmPassword}
              onChange={setConfirmPassword}
              disabled={mode !== 'register'}
              error={confirmPassword !== '' && registerPassword !== confirmPassword ? '两次的密码不匹配' : ''}
            />

            <AuthButton disabled={!canRegister || mode !== 'register'} loading={loading}>
              注册
            </AuthButton>
          </form>
        </motion.div>

        <motion.div
          animate={{
            left: mode === 'login' ? 'calc(100% - 430px)' : 0,
            borderRadius: mode === 'login' ? '0 10px 10px 0' : '10px 0 0 10px'
          }}
          transition={{ duration: 0.45, ease: 'easeInOut' }}
          className="absolute top-1/2 z-20 hidden h-[430px] w-[430px] -translate-y-1/2 flex-col bg-white bg-cover p-9 text-[#1f2937] shadow-2xl md:flex"
          style={{ backgroundImage: `url(${slidingForm})` }}
        >
          <h1 aria-label="HX-Email" className="mb-9 text-[34px] font-light">
            HX<span className="font-bold text-[#24d97f]">-Email</span>
          </h1>
          <div className="mb-9 text-justify text-base leading-7 text-[#1f2937]">
            多邮箱统一管理平台，集中管理账号、临时邮箱、平台绑定与验证码读取流程。
          </div>
          <div className="mt-auto text-base text-[#5777c6]">
            {mode === 'login' ? '新用户?' : '已拥有账号'}
            <button
              type="button"
              onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
              className="ml-3 rounded-md border-0 bg-[#24d97f] px-4 py-1.5 text-sm text-[#102016] outline-none transition hover:brightness-110"
            >
              {mode === 'login' ? '去注册' : '去登录'}
            </button>
          </div>
        </motion.div>

        <button
          type="button"
          onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
          className="absolute bottom-0 z-40 rounded-md border border-white/20 bg-black/35 px-4 py-2 text-sm text-white backdrop-blur md:hidden"
        >
          {mode === 'login' ? '新用户? 去注册' : '已拥有账号，去登录'}
        </button>
      </div>
    </div>
  )
}
