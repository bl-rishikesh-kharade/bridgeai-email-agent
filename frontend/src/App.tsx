import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { ArrowUp, LoaderCircle, LogOut, Mail, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";

type AuthStatus = { connected: boolean; email?: string | null; detail?: string; redirect?: string };
type ChatEmailOption = {
  id: string;
  gmail_url?: string | null;
  subject: string;
  sender: string;
  receiver?: string | null;
  body_snippet?: string | null;
  received_at?: string | null;
  priority?: "Critical" | "High" | "Medium" | "Low" | null;
};
type ChatResponse = {
  response: string;
  email_options?: ChatEmailOption[];
  used_recent_window?: boolean;
  detail?: string;
};
type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  time: Date;
  emailOptions?: ChatEmailOption[];
};

const IMPORTANT_PROMPT = "Show my unread important emails";

function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [switchingAccount, setSwitchingAccount] = useState(false);
  const [authError, setAuthError] = useState("");
  // Browser-only display state. Each request sends only the new message; chat history is not saved.
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [usedRecentWindow, setUsedRecentWindow] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    void checkAuth();
  }, []);

  useEffect(() => {
    if (messages.length > 0 || busy) {
      window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
    }
  }, [messages, busy]);

  async function checkAuth() {
    setCheckingAuth(true);
    setAuthError("");
    try {
      const response = await fetch("/auth/status", { cache: "no-store" });
      const data = await response.json().catch(() => ({})) as AuthStatus;
      if (!response.ok) throw new Error(data.detail || "Could not check the Google connection.");
      setAuth(data);
    } catch (caught) {
      setAuth({ connected: false });
      setAuthError(caught instanceof Error ? caught.message : "Could not reach BridgeAI.");
    } finally {
      setCheckingAuth(false);
    }
  }

  async function connectGoogle() {
    setConnecting(true);
    setAuthError("");
    try {
      const response = await fetch("/auth/connect", { method: "POST" });
      const data = await response.json().catch(() => ({})) as AuthStatus;
      if (!response.ok) throw new Error(data.detail || "Google authorization could not be completed.");
      if (data.redirect) {
        window.location.href = data.redirect;
        return;
      }
      setAuth(data);
    } catch (caught) {
      setAuthError(caught instanceof Error ? caught.message : "Google authorization could not be completed.");
    } finally {
      setConnecting(false);
    }
  }

  async function switchGoogleAccount() {
    setSwitchingAccount(true);
    setError("");
    try {
      const response = await fetch("/auth/disconnect", { method: "POST" });
      const data = await response.json().catch(() => ({})) as AuthStatus;
      if (!response.ok) throw new Error(data.detail || "The Google account could not be disconnected.");
      setMessages([]);
      setDraft("");
      setUsedRecentWindow(false);
      setAuthError("");
      setAuth(data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The Google account could not be disconnected.");
    } finally {
      setSwitchingAccount(false);
    }
  }

  async function submitMessage(text: string, filterId?: "important_unread") {
    const clean = text.trim();
    if (!clean || busy) return;
    setError("");
    const historyPayload = messages.slice(-10).map((m) => ({
      role: m.role,
      text: m.text,
    }));
    setMessages((current) => [...current, {
      id: crypto.randomUUID(), role: "user", text: clean, time: new Date(),
    }]);
    setDraft("");
    setBusy(true);
    try {
      const response = await fetch("/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: clean, filter_id: filterId, history: historyPayload }),
      });
      const data = await response.json().catch(() => ({})) as Partial<ChatResponse>;
      if (!response.ok) throw new Error(data.detail || `The request failed (${response.status}).`);
      setUsedRecentWindow(data.used_recent_window ?? false);
      setMessages((current) => [...current, {
        id: crypto.randomUUID(), role: "assistant", text: data.response || "I couldn't complete that request.",
        time: new Date(), emailOptions: data.email_options,
      }]);
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "The request could not be completed.";
      setError(message);
      setMessages((current) => [...current, {
        id: crypto.randomUUID(), role: "assistant", text: "I couldn't complete that request. Please try again.", time: new Date(),
      }]);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submitMessage(draft);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      inputRef.current?.form?.requestSubmit();
    }
  }

  if (checkingAuth) {
    return <div className="auth-screen"><div className="auth-card"><LoaderCircle className="spin" size={24} /><span>Checking your Google connection…</span></div></div>;
  }

  if (!auth?.connected) {
    return (
      <div className="auth-screen">
        <header className="topbar auth-topbar">
          <a className="brand" href="/" aria-label="BridgeAI Email Agent home">
            <span className="brand-mark"><Mail size={19} /></span>
            <span className="brand-text"><strong>BridgeAI</strong><span>Email Agent</span></span>
          </a>
        </header>
        <main className="auth-main">
          <section className="auth-card">
            <div className="auth-icon"><Mail size={24} /></div>
            <div className="eyebrow"><span className="eyebrow-dot" /> YOUR EMAIL WORKSPACE</div>
            <h1>Connect your Google account</h1>
            <p>BridgeAI uses read-only Gmail access to find and review your emails. Your Google account stays in control of the permission.</p>
            {authError && <div className="inline-error" role="status">{authError}</div>}
            <button className="primary-button connect-button" type="button" onClick={() => void connectGoogle()} disabled={connecting}>
              {connecting ? <LoaderCircle size={17} className="spin" /> : <Mail size={17} />}
              {connecting ? "Waiting for Google authorization…" : "Connect Google"}
            </button>
            <button className="auth-refresh" type="button" onClick={() => void checkAuth()} disabled={connecting}><RefreshCw size={14} /> Check connection again</button>
            <p className="auth-privacy"><ShieldCheck size={14} /> Authorization is saved locally in token.json on this computer.</p>
          </section>
        </main>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <header className="topbar app-topbar">
        <a className="brand" href="/" aria-label="BridgeAI Email Agent home">
          <span className="brand-mark"><Mail size={19} /></span>
          <span className="brand-text"><strong>BridgeAI</strong><span>Email Agent</span></span>
        </a>
        <div className="topbar-right">
          {auth.email && <span className="connected-account">{auth.email}</span>}
          <button className="switch-account-button" type="button" onClick={() => void switchGoogleAccount()} disabled={busy || switchingAccount}>
            {switchingAccount ? <LoaderCircle size={14} className="spin" /> : <LogOut size={14} />}
            {switchingAccount ? "Switching…" : "Switch account"}
          </button>
        </div>
      </header>

      <main className="workspace local-chat-workspace">
        <section className="welcome-row">
          <div>
            <div className="eyebrow"><span className="eyebrow-dot" /> YOUR EMAIL WORKSPACE</div>
            <h1>What would you like to work on?</h1>
            <p>Ask BridgeAI about your mailbox, or start with unread important emails.</p>
          </div>
          <div className="today-card">{new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(new Date())}</div>
        </section>

        <section className="chat-card" aria-label="Email Agent conversation">
          <div className="chat-card-head">
            <div className="agent-avatar"><Sparkles size={18} /></div>
            <div className="chat-title"><h2>Email Agent</h2><span>Connected to Gmail</span></div>
            <button className="filter-chip important-chip" type="button" disabled={busy} onClick={() => void submitMessage(IMPORTANT_PROMPT, "important_unread")}>
              <Mail size={15} /><span>Unread important</span>
            </button>
          </div>

          <div className="chat-body">
            {messages.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon"><Sparkles size={24} /></div>
                <h3>Your email assistant is ready</h3>
                <p>Ask a question about your email, or select <strong>Unread important</strong> to see messages Gmail has marked important that you haven’t read.</p>
              </div>
            ) : (
              <div className="message-list">
                {messages.map((message) => (
                  <article className={`message-row ${message.role}`} key={message.id}>
                    {message.role === "assistant" && <div className="message-avatar"><Sparkles size={15} /></div>}
                    <div className="message-content">
                      <div className={`message-bubble ${message.role}`}>{message.text}</div>
                      {message.role === "assistant" && message.emailOptions?.length ? (
                        <div className="email-options" aria-label="Matching emails">
                          {message.emailOptions.map((email) => (
                            <article className="email-option" key={email.id}>
                              <div className="email-option-copy">
                                <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                                  {email.priority && (
                                    <span className={`priority-badge priority-${email.priority.toLowerCase()}`}>
                                      {email.priority}
                                    </span>
                                  )}
                                  <strong>{email.subject || "(No subject)"}</strong>
                                </div>
                                <span>
                                  {email.sender}
                                  {email.received_at ? ` · ${new Date(email.received_at).toLocaleString()}` : ""}
                                </span>
                              </div>
                              {email.gmail_url && <a className="email-view-link" href={email.gmail_url} target="_blank" rel="noopener noreferrer">View in Gmail</a>}
                            </article>
                          ))}
                        </div>
                      ) : null}
                      <time className="message-time" dateTime={message.time.toISOString()}>{message.time.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}</time>
                    </div>
                  </article>
                ))}
                {busy && <div className="message-row assistant"><div className="message-avatar"><Sparkles size={15} /></div><div className="message-content"><div className="message-bubble loading-bubble"><LoaderCircle size={16} className="spin" /> Checking your request…</div></div></div>}
              </div>
            )}
          </div>

          {usedRecentWindow && <p className="filter-window-notice">There are more than 100 unread important emails, so this result is limited to the last 48 hours.</p>}
          <form className="composer" onSubmit={handleSubmit}>
            {error && <div className="inline-error" role="status">{error}</div>}
            <div className="composer-box">
              <textarea ref={inputRef} value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleKeyDown} maxLength={4000} placeholder="Message your Email Agent…" aria-label="Message your Email Agent" rows={1} />
              <button className="send-button" type="submit" disabled={busy || !draft.trim()} aria-label="Send message" title="Send message">
                {busy ? <LoaderCircle size={17} className="spin" /> : <ArrowUp size={18} />}
              </button>
            </div>
            <div className="composer-foot"><span>Enter to send · Shift + Enter for a new line</span><span>{draft.length}/4000</span></div>
          </form>
        </section>
        <p className="privacy-note"><ShieldCheck size={14} /> Gmail checks run directly through your Google account. Email content is sent to Gemini when you ask for an AI response.</p>
      </main>
    </div>
  );
}

export default App;
