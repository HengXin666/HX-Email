import { request } from '../core'
import type { AuthResponse, User } from '../../types'

export const authApi = {
  login: (username: string, password: string) =>
    request<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    }),

  register: (username: string, password: string) =>
    request<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify({ username, password })
    }),

  logout: () => request<void>('/auth/logout', { method: 'POST' }),

  updateCredentials: (username: string, password: string) =>
    request<{ user: User }>('/auth/me/credentials', {
      method: 'PUT',
      body: JSON.stringify({ username, password })
    })
}
