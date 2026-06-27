export interface User {
  id: number
  username: string
  is_admin: boolean
}

export interface AuthResponse {
  access_token: string
  user: User
}

export interface AdminUserSummary {
  id: number
  username: string
  is_admin: boolean
  email_account_count: number
  usable_email_count: number
}
