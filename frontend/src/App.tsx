import { useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { ArrowUp, Check, LoaderCircle, LogOut, Mail, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import Markdown from "react-markdown";

type AuthStatus = { connected: boolean; email?: string | null; detail?: string; redirect?: string };
type ChatEmailOption = {
  id: string;
  gmail_url?: string | null;
  subject: string;
  sender: string;
  receiver?: string | null;
  body_snippet?: string | null;
  received_at?: string | null;
  summary?: string | null;
  priority?: "Critical" | "High" | "Medium" | "Low" | null;
};
type ChatResponse = {
  response: string;
  email_options?: ChatEmailOption[];
  used_recent_window?: boolean;
  auth_required?: boolean;
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
  const [selectedEmailIds, setSelectedEmailIds] = useState<Set<string>>(new Set());
  const [markedReadIds, setMarkedReadIds] = useState<Set<string>>(new Set());
  const [markingRead, setMarkingRead] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  function toggleSelectEmail(id: string) {
    setSelectedEmailIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }

  function toggleSelectAll(options: ChatEmailOption[]) {
    const unreadOptions = options.filter((e) => !markedReadIds.has(e.id));
    const allSelected = unreadOptions.every((e) => selectedEmailIds.has(e.id));
    setSelectedEmailIds((prev) => {
      const next = new Set(prev);
      if (allSelected) {
        unreadOptions.forEach((e) => next.delete(e.id));
      } else {
        unreadOptions.forEach((e) => next.add(e.id));
      }
      return next;
    });
  }

  async function handleMarkSelectedAsRead(idsToMark: string[]) {
    if (idsToMark.length === 0 || markingRead) return;
    setMarkingRead(true);
    try {
      const response = await fetch("/agent/emails/mark-read", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email_ids: idsToMark }),
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok && data.success) {
        setMarkedReadIds((prev) => {
          const next = new Set(prev);
          idsToMark.forEach((id) => next.add(id));
          return next;
        });
        setSelectedEmailIds((prev) => {
          const next = new Set(prev);
          idsToMark.forEach((id) => next.delete(id));
          return next;
        });
      }
    } catch (err) {
      console.error("Failed to mark emails as read", err);
    } finally {
      setMarkingRead(false);
    }
  }

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
      // Don't disconnect if user was already connected during a transient network blip
      setAuth((current) => (current?.connected ? current : { connected: false }));
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
      if (data.auth_required) {
        // Attempt silent background refresh before kicking user out
        try {
          const refreshRes = await fetch("/auth/status", { cache: "no-store" });
          const refreshData = await refreshRes.json().catch(() => ({})) as AuthStatus;
          if (refreshData?.connected) {
            setAuth(refreshData);
            // Successfully refreshed silently; don't disrupt the user
            return;
          }
        } catch {
          // Ignore error and fall through
        }
        setAuth({ connected: false });
        setAuthError("Your Google session has expired. Please connect your Google account to continue.");
        return;
      }
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
            <p className="auth-privacy"><ShieldCheck size={14} /> Authorization is encrypted and your credentials stay private.</p>
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
                      <div className={`message-bubble ${message.role}`}>
                        {message.role === "assistant" ? (
                          <div className="markdown-content">
                            <Markdown>{message.text}</Markdown>
                          </div>
                        ) : (
                          message.text
                        )}
                      </div>
                      {message.role === "assistant" && message.emailOptions?.length ? (
                        <div className="email-options-container" aria-label="Matching emails">
                          {(() => {
                            const unreadList = message.emailOptions.filter((e) => !markedReadIds.has(e.id));
                            const selectedCount = unreadList.filter((e) => selectedEmailIds.has(e.id)).length;
                            const isAllSelected = unreadList.length > 0 && selectedCount === unreadList.length;

                            return (
                              <div className="email-list-toolbar">
                                <label className="select-all-label">
                                  <input
                                    type="checkbox"
                                    className="custom-checkbox"
                                    checked={isAllSelected}
                                    disabled={unreadList.length === 0}
                                    onChange={() => toggleSelectAll(message.emailOptions!)}
                                  />
                                  <span>Select all ({unreadList.length})</span>
                                </label>
                                <button
                                  type="button"
                                  className={`mark-read-button ${selectedCount > 0 ? "active" : ""}`}
                                  disabled={selectedCount === 0 || markingRead}
                                  onClick={() => {
                                    const idsToMark = unreadList
                                      .filter((e) => selectedEmailIds.has(e.id))
                                      .map((e) => e.id);
                                    void handleMarkSelectedAsRead(idsToMark);
                                  }}
                                >
                                  {markingRead ? (
                                    <>
                                      <LoaderCircle size={14} className="spin" />
                                      <span>Marking…</span>
                                    </>
                                  ) : (
                                    <>
                                      <Check size={14} />
                                      <span>{selectedCount > 0 ? `Mark as read (${selectedCount})` : "Mark as read"}</span>
                                    </>
                                  )}
                                </button>
                              </div>
                            );
                          })()}

                          <div className="email-options">
                            {message.emailOptions.map((email) => {
                              const isMarked = markedReadIds.has(email.id);
                              const isChecked = selectedEmailIds.has(email.id);

                              return (
                                <article className={`email-option ${isMarked ? "is-read-marked" : ""}`} key={email.id}>
                                  <div className="email-option-left">
                                    <input
                                      type="checkbox"
                                      className="custom-checkbox email-card-checkbox"
                                      checked={isChecked}
                                      disabled={isMarked}
                                      onChange={() => toggleSelectEmail(email.id)}
                                      aria-label={`Select ${email.subject}`}
                                    />
                                  </div>
                                  <div className="email-option-copy">
                                    <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
                                      {email.priority && (
                                        <span className={`priority-badge priority-${email.priority.toLowerCase()}`}>
                                          {email.priority}
                                        </span>
                                      )}
                                      <strong>{email.subject || "(No subject)"}</strong>
                                      {isMarked && (
                                        <span className="marked-read-badge">
                                          <Check size={11} /> Read in Gmail
                                        </span>
                                      )}
                                    </div>
                                    <span>
                                      {email.sender}
                                      {email.received_at ? ` · ${new Date(email.received_at).toLocaleString()}` : ""}
                                    </span>
                                    {email.summary ? (
                                      <p className="email-option-summary">{email.summary}</p>
                                    ) : null}
                                  </div>
                                  {email.gmail_url && (
                                    <a className="email-view-link" href={email.gmail_url} target="_blank" rel="noopener noreferrer">
                                      View in Gmail
                                    </a>
                                  )}
                                </article>
                              );
                            })}
                          </div>
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
