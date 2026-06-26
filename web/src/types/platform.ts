export interface Platform {
  id: number
  name: string
  binding_count?: number
}

export type BindingStatus =
  | 'active'
  | 'pending_verification'
  | 'risk'
  | 'disabled'
  | 'archived'

export interface PlatformBinding {
  id: number
  usable_email_id: number
  platform: Platform
  status: BindingStatus
  notes: string
}
