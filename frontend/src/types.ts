export type AuthStatus = {
  connected: boolean;
  email?: string | null;
  detail?: string;
  redirect?: string;
};

export type ChatEmailOption = {
  id: string;
  gmail_url?: string | null;
  meeting_url?: string | null;
  subject: string;
  sender: string;
  receiver?: string | null;
  body_snippet?: string | null;
  received_at?: string | null;
  summary?: string | null;
  priority?: "Critical" | "High" | "Medium" | "Low" | null;
};

export type ChatResponse = {
  response: string;
  email_options?: ChatEmailOption[];
  used_recent_window?: boolean;
  auth_required?: boolean;
  detail?: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  time: Date;
  emailOptions?: ChatEmailOption[];
};
