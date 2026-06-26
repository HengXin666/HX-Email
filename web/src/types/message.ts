export interface TempMessage {
  id: string
  from_address: string
  subject: string
  text: string
  html?: string
  received_at?: string
}

export interface VerificationMatch {
  code: string | null
  link: string | null
  recipient_address: string
  certainty: 'high' | 'medium' | 'low'
  subject: string
  received_at?: string
}
