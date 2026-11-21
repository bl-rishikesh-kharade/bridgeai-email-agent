import React, { useRef, useEffect } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { ArrowUp, Mail, ShieldCheck } from "lucide-react";

interface ChatComposerProps {
  draft: string;
  busy: boolean;
  error: string;
  onDraftChange: (value: string) => void;
  onSubmitMessage: (text: string, filterId?: "important_unread") => void;
}

const IMPORTANT_PROMPT = "Show my unread important emails";

export const ChatComposer: React.FC<ChatComposerProps> = ({
  draft,
  busy,
  error,
  onDraftChange,
  onSubmitMessage,
}) => {
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!busy && inputRef.current) {
      inputRef.current.focus();
    }
  }, [busy]);

  function handleSubmit(event?: FormEvent) {
    if (event) event.preventDefault();
    if (!draft.trim() || busy) return;
    onSubmitMessage(draft);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  return (
    <form className="composer" onSubmit={handleSubmit}>
      <div className="composer-shortcuts">
        <button
          className="shortcut-chip important-chip"
          type="button"
          disabled={busy}
          onClick={() => onSubmitMessage(IMPORTANT_PROMPT, "important_unread")}
          title="Filter and summarize unread important emails"
        >
          <Mail size={14} />
          <span>Unread important</span>
        </button>
      </div>

      {error && (
        <div className="inline-error" role="status">
          {error}
        </div>
      )}

      <div className="composer-box">
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Message your Email Agent…"
          rows={1}
          maxLength={4000}
          disabled={busy}
          aria-label="Message your Email Agent"
        />
        <button
          className="send-button"
          type="submit"
          disabled={busy || !draft.trim()}
          title="Send message"
        >
          <ArrowUp size={16} />
        </button>
      </div>

      <div className="composer-foot">
        <span>Enter to send · Shift + Enter for a new line</span>
        <span>{draft.length}/4000</span>
      </div>

      <div className="privacy-note" style={{ marginTop: "10px" }}>
        <ShieldCheck size={14} />
        <span>Connected securely to Gmail. Your emails are processed in real time and never stored.</span>
      </div>
    </form>
  );
};
