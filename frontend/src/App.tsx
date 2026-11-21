import { useEffect, useState } from "react";
import { LoaderCircle, Mail, RefreshCw, ShieldCheck, Sparkles } from "lucide-react";
import Markdown from "react-markdown";

import type { AuthStatus, ChatEmailOption, ChatResponse, Message } from "./types";
import { Navbar } from "./components/Navbar";
import { EmailCard } from "./components/EmailCard";
import { EmailActionToolbar } from "./components/EmailActionToolbar";
import { ChatComposer } from "./components/ChatComposer";

function App() {
  const [auth, setAuth] = useState<AuthStatus | null>(null);
  const [checkingAuth, setCheckingAuth] = useState(true);
  const [connecting, setConnecting] = useState(false);
  const [switchingAccount, setSwitchingAccount] = useState(false);
  const [authError, setAuthError] = useState("");

  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [selectedEmailIds, setSelectedEmailIds] = useState<Set<string>>(new Set());
  const [markedReadIds, setMarkedReadIds] = useState<Set<string>>(new Set());
  const [markingRead, setMarkingRead] = useState(false);

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
      const data = (await response.json().catch(() => ({}))) as AuthStatus;
      if (!response.ok) throw new Error(data.detail || "Could not check the Google connection.");
      setAuth(data);
    } catch (caught) {
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
      const data = (await response.json().catch(() => ({}))) as AuthStatus;
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
      const data = (await response.json().catch(() => ({}))) as AuthStatus;
      if (!response.ok) throw new Error(data.detail || "The Google account could not be disconnected.");
      setMessages([]);
      setDraft("");
      setAuthError("");
      setAuth(data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "The Google account could not be disconnected.");
    } finally {
      setSwitchingAccount(false);
    }
  }

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

  async function submitMessage(text: string, filterId?: "important_unread") {
    const clean = text.trim();
    if (!clean || busy) return;
    setError("");
    const historyPayload = messages.slice(-10).map((m) => ({
      role: m.role,
      text: m.text,
    }));
    setMessages((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        role: "user",
        text: clean,
        time: new Date(),
      },
    ]);
    setDraft("");
    setBusy(true);

    const abortController = new AbortController();
    const timeoutId = window.setTimeout(() => abortController.abort(), 45000);

    try {
      const response = await fetch("/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: clean, filter_id: filterId, history: historyPayload }),
        signal: abortController.signal,
      });
      clearTimeout(timeoutId);
      const data = (await response.json().catch(() => ({}))) as Partial<ChatResponse>;
      if (!response.ok) throw new Error(data.detail || `The request failed (${response.status}).`);

      if (data.auth_required) {
        // Attempt silent background refresh before prompting user
        try {
          const refreshRes = await fetch("/auth/status", { cache: "no-store" });
          const refreshData = (await refreshRes.json().catch(() => ({}))) as AuthStatus;
          if (refreshData?.connected) {
            setAuth(refreshData);
            return;
          }
        } catch {
          // Fall through
        }
        setAuth({ connected: false });
        setAuthError("Your Google authorization has expired. Please connect your Google account to continue.");
        return;
      }

      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: data.response || "I couldn't complete that request.",
          time: new Date(),
          emailOptions: data.email_options,
        },
      ]);
    } catch (caught) {
      clearTimeout(timeoutId);
      const isTimeout = caught instanceof Error && caught.name === "AbortError";
      const message = isTimeout
        ? "The request timed out while communicating with Gmail. Please try again."
        : caught instanceof Error
        ? caught.message
        : "The request could not be completed.";
      setError(message);
      setMessages((current) => [
        ...current,
        {
          id: crypto.randomUUID(),
          role: "assistant",
          text: isTimeout
            ? (filterId === "important_unread"
                ? "The request took longer than expected while fetching from Gmail. Please click **Unread important** again to retry."
                : "The request took longer than expected while contacting Gmail. Please try your request again.")
            : message.includes("504")
            ? "The cloud server timed out while contacting Gmail. Please try again."
            : "I couldn't complete that request right now. Please try again.",
          time: new Date(),
        },
      ]);
    } finally {
      clearTimeout(timeoutId);
      setBusy(false);
    }
  }

  // Loading spinner during initial auth check
  if (checkingAuth) {
    return (
      <div className="auth-screen" style={{ display: "grid", placeItems: "center" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "12px", color: "#64748b" }}>
          <LoaderCircle size={28} className="spin" style={{ color: "#3b82f6" }} />
          <span style={{ fontSize: "13px", fontWeight: 500 }}>Connecting to your workspace…</span>
        </div>
      </div>
    );
  }

  // Scenario 1: Not connected or session revoked -> Render login screen
  if (!auth?.connected) {
    return (
      <div className="auth-screen">
        <header className="topbar auth-topbar">
          <a className="brand" href="/" aria-label="BridgeAI Email Agent home">
            <span className="brand-mark">
              <Mail size={19} />
            </span>
            <span className="brand-text">
              <strong>BridgeAI</strong>
              <span>Email Agent</span>
            </span>
          </a>
        </header>
        <main className="auth-main">
          <section className="auth-card">
            <div className="auth-icon">
              <Mail size={24} />
            </div>
            <div className="eyebrow">
              <span className="eyebrow-dot" /> YOUR EMAIL WORKSPACE
            </div>
            <h1>Connect your Google account</h1>
            <p>
              BridgeAI uses secure Gmail access to find, summarize, and prioritize your emails.
              Your Google account remains fully in control.
            </p>
            {authError && (
              <div className="inline-error" role="status">
                {authError}
              </div>
            )}
            <button
              className="primary-button connect-button"
              type="button"
              onClick={() => void connectGoogle()}
              disabled={connecting}
            >
              {connecting ? <LoaderCircle size={17} className="spin" /> : <Mail size={17} />}
              {connecting ? "Waiting for Google authorization…" : "Connect Google"}
            </button>
            <button
              className="auth-refresh"
              type="button"
              onClick={() => void checkAuth()}
              disabled={connecting}
            >
              <RefreshCw size={14} /> Check connection again
            </button>
            <p className="auth-privacy">
              <ShieldCheck size={14} /> Authorization is encrypted and credentials stay private.
            </p>
          </section>
        </main>
      </div>
    );
  }

  // Scenario 2 & 3: Connected -> Direct chat workspace with silent background refresh
  return (
    <div className="app-shell">
      <Navbar
        email={auth.email}
        busy={busy}
        switchingAccount={switchingAccount}
        onSwitchAccount={() => void switchGoogleAccount()}
      />

      <main className="workspace local-chat-workspace">
        <section className="welcome-row">
          <div>
            <div className="eyebrow">
              <span className="eyebrow-dot" /> YOUR EMAIL WORKSPACE
            </div>
            <h1>What would you like to work on?</h1>
            <p>Ask BridgeAI about your mailbox, or start with unread important emails.</p>
          </div>
          <div className="today-card">
            {new Intl.DateTimeFormat(undefined, {
              weekday: "short",
              month: "short",
              day: "numeric",
            }).format(new Date())}
          </div>
        </section>

        <section className="chat-card" aria-label="Email Agent conversation">
          <div className="chat-card-head">
            <div className="agent-avatar">
              <Sparkles size={18} />
            </div>
            <div className="chat-title">
              <h2>Email Agent</h2>
              <span>Connected to Gmail</span>
            </div>
          </div>

          <div className="chat-body">
            {messages.length === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">
                  <Sparkles size={24} />
                </div>
                <h3>Your email assistant is ready</h3>
                <p>
                  Ask BridgeAI anything about your inbox, or click{" "}
                  <strong>Unread important</strong> below to review emails that need your attention.
                </p>
              </div>
            ) : (
              <div className="message-list">
                {messages.map((message) => (
                  <article className={`message-row ${message.role}`} key={message.id}>
                    {message.role === "assistant" && (
                      <div className="message-avatar">
                        <Sparkles size={15} />
                      </div>
                    )}
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

                      {message.emailOptions && message.emailOptions.length > 0 && (
                        <div className="email-options-container">
                          <EmailActionToolbar
                            options={message.emailOptions}
                            selectedEmailIds={selectedEmailIds}
                            markedReadIds={markedReadIds}
                            markingRead={markingRead}
                            onToggleSelectAll={() => toggleSelectAll(message.emailOptions!)}
                            onMarkSelectedAsRead={() => {
                              const idsToMark = message
                                .emailOptions!.filter(
                                  (e) => selectedEmailIds.has(e.id) && !markedReadIds.has(e.id)
                                )
                                .map((e) => e.id);
                              void handleMarkSelectedAsRead(idsToMark);
                            }}
                          />

                          <div className="email-options">
                            {message.emailOptions.map((email) => (
                              <EmailCard
                                key={email.id}
                                email={email}
                                isSelected={selectedEmailIds.has(email.id)}
                                isMarkedRead={markedReadIds.has(email.id)}
                                onToggleSelect={toggleSelectEmail}
                              />
                            ))}
                          </div>
                        </div>
                      )}

                      <time className="message-time" dateTime={message.time.toISOString()}>
                        {message.time.toLocaleTimeString([], {
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                      </time>
                    </div>
                  </article>
                ))}

                {busy && (
                  <div className="message-row assistant">
                    <div className="message-avatar">
                      <Sparkles size={15} />
                    </div>
                    <div className="message-content">
                      <div className="message-bubble loading-bubble">
                        <LoaderCircle size={16} className="spin" /> Analyzing your inbox and preparing summaries…
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          <ChatComposer
            draft={draft}
            busy={busy}
            error={error}
            onDraftChange={setDraft}
            onSubmitMessage={(text, filterId) => void submitMessage(text, filterId)}
          />
        </section>
      </main>
    </div>
  );
}

export default App;
