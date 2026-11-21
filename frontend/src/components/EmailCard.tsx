import React from "react";
import { Check, Video } from "lucide-react";
import type { ChatEmailOption } from "../types";

interface EmailCardProps {
  email: ChatEmailOption;
  isSelected: boolean;
  isMarkedRead: boolean;
  onToggleSelect: (id: string) => void;
}

function renderLinkifiedText(text: string) {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  const parts = text.split(urlRegex);
  return parts.map((part, index) => {
    if (part.match(urlRegex)) {
      return (
        <a
          key={index}
          href={part}
          target="_blank"
          rel="noopener noreferrer"
          className="email-inline-link"
        >
          {part}
        </a>
      );
    }
    return part;
  });
}

function formatReceivedDate(dateStr?: string | null): string {
  if (!dateStr) return "";
  try {
    return new Date(dateStr).toLocaleString([], {
      dateStyle: "short",
      timeStyle: "short",
    });
  } catch {
    return "";
  }
}

export const EmailCard: React.FC<EmailCardProps> = ({
  email,
  isSelected,
  isMarkedRead,
  onToggleSelect,
}) => {
  const formattedDate = formatReceivedDate(email.received_at);

  return (
    <div className={`email-option ${isMarkedRead ? "is-read-marked" : ""}`}>
      <div className="email-option-left">
        {isMarkedRead ? (
          <span className="marked-read-badge" title="Marked as read">
            <Check size={11} /> Read
          </span>
        ) : (
          <input
            type="checkbox"
            className="custom-checkbox"
            checked={isSelected}
            onChange={() => onToggleSelect(email.id)}
            aria-label={`Select ${email.subject}`}
          />
        )}
      </div>

      <div className="email-option-copy">
        <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
          {email.priority && (
            <span className={`priority-badge priority-${email.priority.toLowerCase()}`}>
              {email.priority}
            </span>
          )}
          <strong>{email.subject}</strong>
        </div>
        <span>
          {email.sender}
          {formattedDate ? ` • ${formattedDate}` : ""}
        </span>
        {email.summary && (
          <div className="email-option-summary">
            {renderLinkifiedText(email.summary)}
          </div>
        )}
      </div>

      <div className="email-option-actions-right">
        {email.meeting_url && (
          <a
            href={email.meeting_url}
            target="_blank"
            rel="noopener noreferrer"
            className="email-action-link email-join-link"
            title="Join video conference call"
          >
            <Video size={13} /> Join Meeting
          </a>
        )}
        {email.gmail_url && (
          <a
            href={email.gmail_url}
            target="_blank"
            rel="noopener noreferrer"
            className="email-action-link email-view-link"
          >
            View in Gmail
          </a>
        )}
      </div>
    </div>
  );
};
