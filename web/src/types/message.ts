export interface TempMessage {
  id: string;
  from_address: string;
  subject: string;
  text: string;
  html?: string;
  received_at?: string;
}

export interface StoredEmailMessage {
  id: number;
  from_address: string;
  recipient_address: string;
  subject: string;
  body: string;
  verification_code?: string | null;
  message_id?: string;
  received_at: string;
  created_at: string;
}

export interface EmailMessagesPage {
  messages: StoredEmailMessage[];
  total: number;
}

export interface VerificationMatch {
  code: string | null;
  link: string | null;
  recipient_address: string | null;
  certainty: string;
  subject: string;
  received_at?: string;
}

export interface VerificationReading {
  matches: VerificationMatch[];
}
