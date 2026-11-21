import React from "react";
import { LoaderCircle } from "lucide-react";
import type { ChatEmailOption } from "../types";

interface EmailActionToolbarProps {
  options: ChatEmailOption[];
  selectedEmailIds: Set<string>;
  markedReadIds: Set<string>;
  markingRead: boolean;
  onToggleSelectAll: () => void;
  onMarkSelectedAsRead: () => void;
}

export const EmailActionToolbar: React.FC<EmailActionToolbarProps> = ({
  options,
  selectedEmailIds,
  markedReadIds,
  markingRead,
  onToggleSelectAll,
  onMarkSelectedAsRead,
}) => {
  const unreadOptions = options.filter((e) => !markedReadIds.has(e.id));
  const selectedCount = unreadOptions.filter((e) => selectedEmailIds.has(e.id)).length;
  const allSelected = unreadOptions.length > 0 && selectedCount === unreadOptions.length;

  if (unreadOptions.length === 0) {
    return null;
  }

  return (
    <div className="email-list-toolbar">
      <label className="select-all-label">
        <input
          type="checkbox"
          className="custom-checkbox"
          checked={allSelected}
          onChange={onToggleSelectAll}
          aria-label="Select all emails"
        />
        <span>Select all ({unreadOptions.length})</span>
      </label>

      <button
        type="button"
        className={`mark-read-button ${selectedCount > 0 ? "active" : ""}`}
        disabled={selectedCount === 0 || markingRead}
        onClick={onMarkSelectedAsRead}
      >
        {markingRead ? (
          <>
            <LoaderCircle size={13} className="spin" />
            <span>Marking…</span>
          </>
        ) : (
          <span>Mark as read ({selectedCount})</span>
        )}
      </button>
    </div>
  );
};
